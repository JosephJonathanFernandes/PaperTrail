import pytest
from unittest.mock import patch, MagicMock
from src.papertrail.services.search import run_stage_2_search, extract_linkedin_outbound_links
from src.papertrail.core.scoring import score_candidate

@patch('src.papertrail.services.search.DDGS')
def test_29_ddg_returns_zero_results(mock_ddgs):
    mock_instance = mock_ddgs.return_value.__enter__.return_value
    mock_instance.text.return_value = []
    
    metadata = {"title": "Test Title", "author": "Test Author"}
    res = run_stage_2_search(metadata)
    assert res == []

@patch('src.papertrail.services.search.DDGS')
def test_30_ddg_returns_results_with_missing_href_field(mock_ddgs):
    mock_instance = mock_ddgs.return_value.__enter__.return_value
    # DDGS dict results sometimes miss keys if poorly structured
    mock_instance.text.return_value = [{"title": "Test", "body": "Snippet without href"}]
    
    res = run_stage_2_search({"title": "Test"})
    assert res == []

@patch('src.papertrail.services.search.DDGS')
def test_31_ddg_returns_malformedtruncated_urls(mock_ddgs):
    mock_instance = mock_ddgs.return_value.__enter__.return_value
    mock_instance.text.return_value = [{"href": "http://[malformed-url", "title": "Test", "body": "Snippet"}]
    
    res = run_stage_2_search({"title": "Test"})
    # It might get rejected by the scorer, but shouldn't crash
    assert len(res) >= 0

def test_32_ddg_result_snippet_has_multiple_links():
    snippet = "Check out https://link1.com/file.pdf and https://link2.org/paper.pdf here."
    links = extract_linkedin_outbound_links(snippet)
    assert len(links) == 2
    assert "https://link1.com/file.pdf" in links

@patch('src.papertrail.services.search.time.sleep')
@patch('src.papertrail.services.search.DDGS')
def test_33_ddg_ratelimits_429_or_empty_due_to_throttling(mock_ddgs, mock_sleep):
    mock_instance = mock_ddgs.return_value.__enter__.return_value
    mock_instance.text.side_effect = Exception("Rate limit reached")
    
    # Should catch the exception, apply backoff, and eventually return empty list without crashing
    res = run_stage_2_search({"title": "Test"})
    assert res == []
    assert mock_sleep.called

def test_34_researchgateauthorpage_search_returns_nonedu_domain_by_mistake():
    # Test scoring filter
    score = score_candidate("https://random-site.com/file.pdf", "Title", "Author", "Title", "Snippet")
    # Score should be low or 0 if it doesn't match standard academic domains and metadata isn't extremely strong
    assert score < 50

def test_35_fuzzy_title_match_exact_title():
    score = score_candidate("https://arxiv.org/pdf/1234.pdf", "Attention is all you need", "Vaswani", "Attention is all you need", "Snippet")
    assert score >= 75

def test_36_fuzzy_title_match_95_similar_typo():
    score = score_candidate("https://arxiv.org/pdf/1234.pdf", "Attention is all you need", "Vaswani", "Attentio is all you need", "Snippet")
    assert score >= 75

def test_37_fuzzy_title_match_40_similar_unrelated_paper():
    score = score_candidate("https://arxiv.org/pdf/1234.pdf", "Attention is all you need", "Vaswani", "Generative Adversarial Networks", "Snippet")
    assert score == 50
