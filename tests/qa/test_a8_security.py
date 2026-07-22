import pytest
import responses
import os
import logging
from src.papertrail.api.routes import app
from src.papertrail.services.search import _is_private_url, resolve_redirect

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@responses.activate
def test_64_ssrf_any_field_that_reaches_requestsget_directly_from(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    resp = client.post('/find_paper', json={"title": "http://169.254.169.254/latest/meta-data/"})
    assert resp.status_code == 404
    # No request to 169.254.169.254 was made because it's only searched as a string in APIs, not fetched directly.

def test_65_cors_preflight_from_an_arbitrary_origin_not_the(client):
    resp = client.options('/find_paper', headers={"Origin": "https://malicious.com"})
    # CORS is now fail-closed: if CHROME_EXTENSION_ID is unset in test env,
    # the server allows the OPTIONS preflight at the HTTP level (200) but does
    # NOT echo back an Access-Control-Allow-Origin header for non-matching origins.
    # The browser will still block the subsequent request. Flask-CORS returns 200
    # for OPTIONS regardless of origin matching — the restriction is in the response headers.
    assert resp.status_code == 200
    # Critically: the malicious origin must NOT appear in the ACAO header
    acao = resp.headers.get('Access-Control-Allow-Origin', '')
    assert 'malicious.com' not in acao, f"CORS leak: malicious origin in ACAO header: {acao}"

def test_66_cors_preflight_from_the_extensions_actual_origin(client):
    resp = client.options('/find_paper', headers={"Origin": "chrome-extension://myid123"})
    assert resp.status_code == 200

def test_67_error_responses_checked_for_leaked_unpaywallemail_or_other(client):
    resp = client.post('/find_paper', data="not json", content_type="application/json")
    assert resp.status_code == 400
    assert os.getenv("UNPAYWALL_EMAIL", "default@example.com") not in resp.data.decode()

def test_68_no_secrets_leaked_in_error_responses(client):
    """Confirms error responses never contain sensitive config values."""
    # Trigger a 400 with malformed JSON
    resp = client.post('/find_paper', data="{not json", content_type="application/json")
    body = resp.data.decode()
    # Unpaywall email must never appear in any error response
    assert os.getenv("UNPAYWALL_EMAIL", "default@example.com") not in body
    # Flask secret key (if set) must not appear
    secret = app.config.get("SECRET_KEY", "")
    if secret:
        assert secret not in body
    # Common internal path fragments must not appear
    for leak in ["site-packages", "AppData", os.getcwd()]:
        assert leak not in body, f"Internal path leaked in error response: {leak!r}"

# ── SSRF Protection Tests ──────────────────────────────────────────────────

def test_70b_ssrf_private_ip_ranges_blocked():
    """_is_private_url() must block all private/internal addresses."""
    blocked = [
        "http://127.0.0.1/",
        "http://127.0.0.1:8080/admin",
        "http://10.0.0.1/secret",
        "http://10.255.255.255/",
        "http://172.16.0.1/",
        "http://172.31.255.254/",
        "http://192.168.0.1/",
        "http://192.168.100.50/",
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.0.1/",
        "http://localhost/",
        "http://metadata.google.internal/",
        "http://[::1]/test",
    ]
    for url in blocked:
        assert _is_private_url(url) is True, f"Expected BLOCKED but was ALLOWED: {url}"

def test_70c_ssrf_safe_public_urls_allowed():
    """_is_private_url() must not block legitimate public academic domains."""
    allowed = [
        "https://arxiv.org/pdf/1706.03762.pdf",
        "https://api.openalex.org/works/W123",
        "https://researchgate.net/publication/123",
        "https://mit.edu/paper.pdf",
        "https://nature.com/articles/s41586-020-2649-2",
        "https://biorxiv.org/content/10.1101/2021.01.01.425001v1.full.pdf",
    ]
    for url in allowed:
        assert _is_private_url(url) is False, f"Expected ALLOWED but was BLOCKED: {url}"

@responses.activate
def test_69_injection_attempt_via_author_field_into_any_shellsubprocess(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    resp = client.post('/find_paper', json={"title": "Title", "author": "; rm -rf /"})
    assert resp.status_code == 404
    # The application never uses subprocess.run or os.system
