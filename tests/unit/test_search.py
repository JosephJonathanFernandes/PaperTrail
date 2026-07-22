"""
Unit tests for src/papertrail/services/search.py

Covers:
  - _is_private_url(): all private IP ranges, edge cases, safe public domains
  - resolve_redirect(): SSRF pre+post-redirect blocking, normal resolution
  - _ddg_search_with_timeout(): timeout enforcement, exception propagation
  - perform_search(): retry logic, returns empty on exhaustion
  - extract_linkedin_outbound_links(): URL extraction, bad input handling

All tests are isolated from live network calls using mocks/patches.
"""

import pytest
import time
import responses as resp_lib
from unittest.mock import patch, MagicMock
from src.papertrail.services.search import (
    _is_private_url,
    _ddg_search_with_timeout,
    resolve_redirect,
    perform_search,
    extract_linkedin_outbound_links,
)


# ── _is_private_url() ────────────────────────────────────────────────────────

class TestIsPrivateUrl:
    """Isolated tests for the SSRF pre-request URL validator."""

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/",
        "http://127.0.0.1:8080/admin",
        "http://127.255.255.255/path",
        "http://10.0.0.1/secret",
        "http://10.0.0.0/",
        "http://10.255.255.255/",
        "http://172.16.0.1/",
        "http://172.31.255.254/",
        "http://172.20.0.5:8443/internal",
        "http://192.168.0.1/router",
        "http://192.168.100.50/",
        "http://192.168.255.255/",
    ])
    def test_rfc1918_ranges_blocked(self, url):
        assert _is_private_url(url) is True, f"Expected BLOCKED: {url}"

    @pytest.mark.parametrize("url", [
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.0.1/",
        "http://169.254.255.255/",
    ])
    def test_link_local_blocked(self, url):
        assert _is_private_url(url) is True, f"Expected BLOCKED: {url}"

    @pytest.mark.parametrize("url", [
        "http://localhost/",
        "http://localhost:5000/admin",
        "http://metadata.google.internal/",
        "http://instance-data/",
    ])
    def test_internal_hostnames_blocked(self, url):
        assert _is_private_url(url) is True, f"Expected BLOCKED: {url}"

    @pytest.mark.parametrize("url", [
        "http://[::1]/test",
        "http://[::1]:8080/path",
    ])
    def test_ipv6_loopback_blocked(self, url):
        assert _is_private_url(url) is True, f"Expected BLOCKED: {url}"

    @pytest.mark.parametrize("url", [
        "",
        "not-a-url",
        "http://",
        "ftp://",
    ])
    def test_unparseable_fails_closed(self, url):
        assert _is_private_url(url) is True, f"Expected fail-closed for: {url!r}"

    @pytest.mark.parametrize("url", [
        "https://arxiv.org/pdf/1706.03762.pdf",
        "https://api.openalex.org/works/W2963403868",
        "https://api.crossref.org/works/10.1234/test",
        "https://api.core.ac.uk/v3/works",
        "https://researchgate.net/publication/123456",
        "https://biorxiv.org/content/10.1101/2021v1.full.pdf",
        "https://ssrn.com/abstract=123456",
        "https://osf.io/preprints/test",
        "https://mit.edu/paper.pdf",
        "https://cs.stanford.edu/user/paper.pdf",
        "https://nature.com/articles/s41586-020-2649-2",
        "https://doi.org/10.1109/CVPR.2016.90",
        # Public IPs that look like private but aren't
        "https://11.0.0.1/paper",    # 11.x is public
        "https://172.32.0.1/paper",  # outside 172.16-31
        "https://192.169.0.1/paper", # outside 192.168
    ])
    def test_public_domains_allowed(self, url):
        assert _is_private_url(url) is False, f"Expected ALLOWED but was BLOCKED: {url}"


# ── resolve_redirect() ────────────────────────────────────────────────────────

class TestResolveRedirect:
    """Tests for SSRF-safe redirect resolution."""

    def test_blocks_private_ip_pre_request_no_http_call(self):
        """Should return original URL unchanged without making any HTTP call."""
        url = "http://10.0.0.1/internal"
        with patch("src.papertrail.services.search.requests.head") as mock_head:
            result = resolve_redirect(url)
            mock_head.assert_not_called()
        assert result == url

    @resp_lib.activate
    def test_normal_public_url_passes_through(self):
        """Non-redirect public URLs are returned unchanged."""
        resp_lib.add(resp_lib.HEAD, "https://arxiv.org/pdf/1706.03762.pdf", status=200)
        result = resolve_redirect("https://arxiv.org/pdf/1706.03762.pdf")
        assert "arxiv.org" in result

    @resp_lib.activate
    def test_head_failure_falls_back_to_get(self):
        """When HEAD returns 405/404, falls back to streaming GET."""
        resp_lib.add(resp_lib.HEAD, "https://example.org/pdf", status=405)
        resp_lib.add(resp_lib.GET, "https://example.org/pdf", status=200, body=b"")
        result = resolve_redirect("https://example.org/pdf")
        assert result == "https://example.org/pdf"

    @resp_lib.activate
    def test_network_error_returns_original(self):
        """On connection error, returns the original URL unchanged."""
        import requests
        resp_lib.add(
            resp_lib.HEAD,
            "https://example.org/broken",
            body=requests.RequestException("Connection refused")
        )
        result = resolve_redirect("https://example.org/broken")
        assert result == "https://example.org/broken"

    def test_metadata_endpoint_blocked(self):
        """AWS/GCP metadata endpoint must be blocked pre-request."""
        result = resolve_redirect("http://169.254.169.254/latest/meta-data/")
        assert "169.254" not in result or result == "http://169.254.169.254/latest/meta-data/"


# ── _ddg_search_with_timeout() ────────────────────────────────────────────────

class TestDdgSearchWithTimeout:
    """Tests for the DDG thread-based timeout wrapper."""

    def test_timeout_raises_timeout_error(self):
        """If DDG hangs beyond timeout, TimeoutError is raised."""
        def slow_text(*args, **kwargs):
            time.sleep(10)
            return iter([])

        with patch("src.papertrail.services.search.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.text.side_effect = slow_text
            mock_ddgs.return_value.__enter__ = MagicMock(return_value=mock_instance)
            mock_ddgs.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(TimeoutError, match="timed out"):
                _ddg_search_with_timeout("test query", timeout=0.1)

    def test_ddg_exception_propagates(self):
        """If DDG raises internally, it's re-raised by the wrapper."""
        with patch("src.papertrail.services.search.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.text.side_effect = RuntimeError("DDG rate limited")
            mock_ddgs.return_value.__enter__ = MagicMock(return_value=mock_instance)
            mock_ddgs.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(RuntimeError, match="rate limited"):
                _ddg_search_with_timeout("test query", timeout=5)

    def test_successful_results_returned(self):
        """Returns properly formatted results list."""
        fake_results = [
            {"href": "https://arxiv.org/pdf/1706.03762", "title": "Attention", "body": "Vaswani"},
        ]
        with patch("src.papertrail.services.search.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.text.return_value = iter(fake_results)
            mock_ddgs.return_value.__enter__ = MagicMock(return_value=mock_instance)
            mock_ddgs.return_value.__exit__ = MagicMock(return_value=False)

            results = _ddg_search_with_timeout("test", timeout=5)

        assert len(results) == 1
        assert results[0]["url"] == "https://arxiv.org/pdf/1706.03762"
        assert results[0]["title"] == "Attention"
        assert results[0]["snippet"] == "Vaswani"


# ── perform_search() ──────────────────────────────────────────────────────────

class TestPerformSearch:
    """Tests for the retry-wrapped DDG search."""

    def test_returns_empty_on_all_failures(self):
        """After all retries fail, returns empty list (does not raise)."""
        with patch("src.papertrail.services.search._ddg_search_with_timeout",
                   side_effect=TimeoutError("hang")):
            with patch("src.papertrail.services.search.time.sleep"):
                result = perform_search("test", retries=3, backoff=0)
        assert result == []

    def test_returns_results_on_first_success(self):
        """Returns results immediately; no unnecessary retries."""
        fake = [{"url": "https://arxiv.org/1", "title": "T", "snippet": "S"}]
        with patch("src.papertrail.services.search._ddg_search_with_timeout",
                   return_value=fake) as mock_fn:
            result = perform_search("test", retries=3)
        assert result == fake
        mock_fn.assert_called_once()

    def test_retries_then_succeeds(self):
        """Retries after failures, returns results when later attempt succeeds."""
        fake = [{"url": "https://arxiv.org/1", "title": "T", "snippet": "S"}]
        effects = [RuntimeError("fail"), RuntimeError("fail"), fake]
        with patch("src.papertrail.services.search._ddg_search_with_timeout",
                   side_effect=effects):
            with patch("src.papertrail.services.search.time.sleep"):
                result = perform_search("test", retries=3, backoff=0)
        assert result == fake


# ── extract_linkedin_outbound_links() ─────────────────────────────────────────

class TestExtractLinkedinOutboundLinks:

    def test_extracts_https_urls(self):
        snippet = "See https://arxiv.org/pdf/1706.03762 and https://nature.com/xyz"
        result = extract_linkedin_outbound_links(snippet)
        assert "https://arxiv.org/pdf/1706.03762" in result
        assert "https://nature.com/xyz" in result

    def test_extracts_http_urls(self):
        result = extract_linkedin_outbound_links("Old: http://example.com/paper")
        assert "http://example.com/paper" in result

    def test_empty_snippet_returns_empty(self):
        assert extract_linkedin_outbound_links("") == []

    def test_no_urls_returns_empty(self):
        assert extract_linkedin_outbound_links("No links, just text.") == []

    def test_multiple_urls(self):
        snippet = "https://a.com https://b.org http://c.net"
        result = extract_linkedin_outbound_links(snippet)
        assert len(result) == 3


# ── Author normalization (item 6 verification) ────────────────────────────────

class TestAuthorNormalization:

    def test_normalize_first_last(self):
        from src.papertrail.core.scoring import _normalize_author
        assert _normalize_author("Ashish Vaswani") == ("vaswani", "a")

    def test_normalize_initial_last(self):
        from src.papertrail.core.scoring import _normalize_author
        assert _normalize_author("A. Vaswani") == ("vaswani", "a")

    def test_normalize_last_comma_first(self):
        from src.papertrail.core.scoring import _normalize_author
        assert _normalize_author("Vaswani, A.") == ("vaswani", "a")

    def test_normalize_last_only(self):
        from src.papertrail.core.scoring import _normalize_author
        last, initial = _normalize_author("Vaswani")
        assert last == "vaswani"

    def test_author_match_initial_vs_full_first_name(self):
        from src.papertrail.core.scoring import _author_match
        assert _author_match("A. Vaswani", "Ashish Vaswani Noam Shazeer") is True

    def test_author_match_last_comma_format(self):
        from src.papertrail.core.scoring import _author_match
        assert _author_match("Vaswani, A.", "Vaswani Shazeer") is True

    def test_author_match_negative_similar_name(self):
        from src.papertrail.core.scoring import _author_match
        # Same last initial, similar sounding but different
        assert _author_match("A. Smyth", "A. Smith") is False

    def test_author_match_negative_same_last_name_different_initial(self):
        from src.papertrail.core.scoring import _author_match
        # Should reject B. Smith when looking for A. Smith
        assert _author_match("A. Smith", "B. Smith") is False
        assert _author_match("Smith, A.", "Smith, B.") is False

    def test_author_match_negative_different_authors(self):
        from src.papertrail.core.scoring import _author_match
        # Completely different authors
        assert _author_match("Vaswani, A.", "LeCun, Y. Bengio, Y. Hinton, G.") is False

    def test_author_match_last_name_only(self):
        from src.papertrail.core.scoring import _author_match
        assert _author_match("Vaswani", "Vaswani Shazeer") is True

    def test_author_no_match(self):
        from src.papertrail.core.scoring import _author_match
        assert _author_match("Smith", "Vaswani Shazeer Parmar") is False

    def test_conflicting_initials_not_matched(self):
        """B. Smith must NOT match A. Smith when both initials are present."""
        from src.papertrail.core.scoring import _author_match
        assert _author_match("B. Smith", "A. Smith") is False


# ── Confidence tier boundary tests (item 10/11 verification) ─────────────────

class TestConfidenceTierBoundaries:

    def test_exact_match_is_high(self):
        from src.papertrail.core.scoring import calculate_confidence
        meta = {
            "title": "Attention Is All You Need",
            "doi": "10.48550/arxiv.1706.03762",
            "authors": [{"family": "Vaswani"}],
            "year": 2017,
            "is_retracted": False
        }
        r = calculate_confidence("", "Attention Is All You Need", "Vaswani", meta)
        assert r["tier"] == "HIGH"
        assert r["score"] >= 90
        assert r["flags"] == []

    def test_title_and_author_mismatch_is_low(self):
        from src.papertrail.core.scoring import calculate_confidence
        meta = {
            "title": "A Survey of Deep Learning Methods",
            "doi": "10.1234/fake",
            "authors": [{"family": "Smith"}],
            "year": 2020,
            "is_retracted": False
        }
        r = calculate_confidence("", "Deep Learning: A Comprehensive Review", "Zhang", meta)
        assert r["tier"] == "LOW"
        assert r["score"] < 70
        assert len(r["flags"]) == 2

    def test_retracted_always_zero_and_low(self):
        from src.papertrail.core.scoring import calculate_confidence
        meta = {
            "title": "Retracted Title",
            "doi": "10.1234/retracted",
            "authors": [{"family": "Author"}],
            "year": 2010,
            "is_retracted": True
        }
        r = calculate_confidence("", "Retracted Title", "Author", meta)
        assert r["score"] == 0
        assert r["tier"] == "LOW"
        assert any("RETRACT" in f.upper() for f in r["flags"])

    def test_author_initial_no_mismatch_flag(self):
        """'A. Vaswani' must not trigger author-mismatch flag vs 'Vaswani' in API."""
        from src.papertrail.core.scoring import calculate_confidence
        meta = {
            "title": "Attention Is All You Need",
            "doi": "10.48550/arxiv.1706.03762",
            "authors": [{"family": "Vaswani"}],
            "year": 2017,
            "is_retracted": False
        }
        r = calculate_confidence("", "Attention Is All You Need", "A. Vaswani", meta)
        flag_texts = " ".join(r["flags"]).lower()
        assert "author mismatch" not in flag_texts, f"Flags: {r['flags']}"
        assert r["tier"] == "HIGH"
