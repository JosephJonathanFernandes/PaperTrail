import pytest
from src.papertrail.core.scoring import is_shadow_library, score_candidate, calculate_confidence

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

def test_calculate_confidence_exact_match():
    metadata = {"title": "Attention Is All You Need", "authors": [{"family": "Vaswani"}]}
    result = calculate_confidence(None, "Attention Is All You Need", "Vaswani", metadata)
    assert result["score"] == 100
    assert result["tier"] == "HIGH"
    assert len(result["flags"]) == 0

def test_calculate_confidence_author_mismatch():
    metadata = {"title": "Attention Is All You Need", "authors": [{"family": "Vaswani"}]}
    result = calculate_confidence(None, "Attention Is All You Need", "Smith", metadata)
    assert result["score"] < 100
    assert any("Author mismatch" in flag for flag in result["flags"])

def test_calculate_confidence_title_drift():
    metadata = {"title": "Attention Is All You Need", "authors": [{"family": "Vaswani"}]}
    # A slightly off title should lower the score but not destroy it completely
    result = calculate_confidence(None, "Attention is what you need", "Vaswani", metadata)
    assert result["score"] < 100
    assert result["score"] > 50
    assert any("Title mismatch" in flag for flag in result["flags"])

def test_calculate_confidence_arxiv_id_exact_match():
    # If the user queried an arXiv ID and the API metadata confirms that ID, it should score 100%
    query = "Layer normalization. arXiv:1607.06450"
    metadata = {
        "title": "Layer Normalization", 
        "authors": [{"family": "Ba"}],
        "doi": "10.48550/arXiv.1607.06450"
    }
    result = calculate_confidence(query, None, None, metadata)
    assert result["score"] == 100
    assert result["tier"] == "HIGH"

def test_calculate_confidence_hallucination():
    # Simulating the OpenAlex hallucination bug (querying a citation, returning ResMLP)
    query = "Jimmy Lei Ba, Jamie Ryan Kiros. Layer normalization. arXiv preprint arXiv:1607.06450, 2016."
    metadata = {
        "title": "ResMLP: Feedforward Networks for Image Classification With Data-Efficient Training",
        "authors": [{"family": "Touvron"}],
        "doi": "10.1109/TPAMI.2022.3206148"
    }
    result = calculate_confidence(query, None, None, metadata)
    assert result["score"] < 70
    assert result["tier"] in ["LOW", "MEDIUM"]
    assert any("hallucinated" in flag.lower() for flag in result["flags"])
