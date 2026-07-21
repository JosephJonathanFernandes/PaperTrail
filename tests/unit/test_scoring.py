import pytest
from src.papertrail.core.scoring import is_shadow_library, score_candidate

def test_is_shadow_library_blocks_known_domains():
    assert is_shadow_library("https://sci-hub.se/10.1234/xyz") == True
    assert is_shadow_library("http://libgen.is/book/123") == True
    assert is_shadow_library("https://annas-archive.org/md5/abc") == True
    assert is_shadow_library("https://mirror.sci-hub.se/file.pdf") == True

def test_is_shadow_library_negative_suite():
    # Make sure we don't overmatch on innocent domains containing bad keywords
    safe_urls = [
        "https://sci-hub-news.com/article",
        "http://my-libgenious-app.io/login",
        "https://z-lib-fans.org",
        "https://arxiv.org/pdf/1234.pdf",
        "https://researchgate.net/publication/123",
        "https://nature.com/articles/s41586-020-2649-2"
    ]
    for url in safe_urls:
        assert is_shadow_library(url) is False, f"Overmatched on safe URL: {url}"

def test_score_candidate_hard_blocks():
    # Should return -1 for shadow libraries
    score = score_candidate(
        url="https://sci-hub.se/file.pdf",
        title="Deep Learning",
        author_lastname="LeCun"
    )
    assert score == -1

def test_score_candidate_ranking():
    # Institutional/Academic domains should score highly (>= 50)
    score = score_candidate(
        url="https://mit.edu/paper.pdf",
        title="Deep Learning",
        author_lastname="LeCun"
    )
    assert score >= 50
