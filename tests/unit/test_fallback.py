import pytest
from src.papertrail.services.fallback import run_stage_3_fallback

def test_run_stage_3_fallback_smoke():
    """
    Smoke test to ensure the fallback logic always returns a properly 
    structured dict, even if the web search fails or returns nothing.
    """
    metadata = {
        "title": "Attention Is All You Need",
        "author": "Vaswani"
    }
    
    result = run_stage_3_fallback(metadata)
    
    # Assert structural integrity
    assert "author_contact_page" in result
    assert "request_fulltext_link" in result
    assert "message" in result
    assert "interlibrary_loan_suggested" in result
    
    assert result["interlibrary_loan_suggested"] is True
    
    # The message should fall back gracefully if DDG doesn't return anything
    assert "No legal Open Access PDF could be found" in result["message"]
