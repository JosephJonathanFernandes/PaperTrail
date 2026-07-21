import pytest
from unittest.mock import patch
from src.papertrail.services.fallback import run_stage_3_fallback, get_researchgate_link

@patch('src.papertrail.services.fallback.DDGS')
def test_56_no_results_anywhere(mock_ddgs):
    mock_instance = mock_ddgs.return_value.__enter__.return_value
    mock_instance.text.return_value = []
    
    options = run_stage_3_fallback({"title": "Test Title", "author": "Test Author"})
    assert isinstance(options, dict)
    assert "message" in options
    assert "Interlibrary Loan" in options["message"] or "author" in options["message"].lower()

@patch('src.papertrail.services.fallback.DDGS')
def test_57_researchgate_page_search_itself_fails_network_error(mock_ddgs):
    mock_instance = mock_ddgs.return_value.__enter__.return_value
    mock_instance.text.side_effect = Exception("Network Error")
    
    link = get_researchgate_link("Test Title", "Test Author")
    assert link is None

@patch('src.papertrail.services.fallback.DDGS')
def test_58_author_name_has_special_characters_eg_mller_obrien(mock_ddgs):
    mock_instance = mock_ddgs.return_value.__enter__.return_value
    mock_instance.text.return_value = [{"href": "https://researchgate.net/publication/Muller"}]
    
    # Should not crash during urllib encoding inside get_researchgate_link or DDG search
    link = get_researchgate_link("Test Title", "Müller O'Brien Nguyễn")
    assert link is not None
