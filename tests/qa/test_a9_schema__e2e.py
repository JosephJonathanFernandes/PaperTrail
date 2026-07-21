import pytest
import responses
from unittest.mock import patch
from src.papertrail.api.routes import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@responses.activate
def test_70_stage_1_success_path_json_shape(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": [{"title": "Test Title", "year": 2020, "authors": [{"name": "Author"}], "externalIds": {"DOI": "10.123"}}]}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.123", json={"is_oa": True, "best_oa_location": {"url_for_pdf": "http://pdf.com"}}, status=200, match_querystring=False)
    
    resp = client.post('/find_paper', json={"title": "Test Title"})
    assert resp.status_code == 200
    data = resp.json
    assert "status" in data
    assert data["status"] == "success"
    assert "pdf_url" in data
    assert "metadata" in data
    assert "confidence_tier" in data

@patch('src.papertrail.services.search.DDGS')
@responses.activate
def test_71_stage_2_success_path_json_shape(mock_ddgs, client):
    mock_instance = mock_ddgs.return_value.__enter__.return_value
    mock_instance.text.return_value = [{"title": "Test Title PDF", "href": "https://arxiv.org/pdf/1234.pdf", "body": "Snippet"}]
    
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": [{"title": "Test Title", "year": 2020, "authors": [{"name": "Author"}]}]}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)

    resp = client.post('/find_paper', json={"title": "Test Title Stage 2"})
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "success"
    assert data["source"] == "search"
    assert data["pdf_url"] == "https://arxiv.org/pdf/1234.pdf"

@patch('src.papertrail.services.fallback.DDGS')
@patch('src.papertrail.services.search.DDGS')
@responses.activate
def test_72_stage_3_fallback_json_shape(mock_search_ddgs, mock_fallback_ddgs, client):
    mock_search_ddgs.return_value.__enter__.return_value.text.return_value = []
    mock_fallback_ddgs.return_value.__enter__.return_value.text.return_value = []
    
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": [{"title": "Test Title", "year": 2020, "authors": [{"name": "Author"}]}]}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)

    resp = client.post('/find_paper', json={"title": "Test Title Stage 3"})
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "not_found"
    assert "fallback_options" in data

@responses.activate
def test_73_unverified_fabricated_json_shape(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    
    resp = client.post('/find_paper', json={"title": "Fabricated Paper XYZ 123"})
    assert resp.status_code == 404
    data = resp.json
    assert data["status"] == "unverified"
    assert data["confidence_tier"] == "NONE"

@patch('src.papertrail.services.fallback.DDGS')
@patch('src.papertrail.services.search.DDGS')
@responses.activate
def test_74_waterfall_stage_1_empty__stage_2_blockeddomainonly(mock_search_ddgs, mock_fallback_ddgs, client):
    mock_search_ddgs.return_value.__enter__.return_value.text.return_value = [{"title": "SciHub", "href": "https://sci-hub.se/123", "body": "Snippet"}]
    mock_fallback_ddgs.return_value.__enter__.return_value.text.return_value = []
    
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": [{"title": "Test Title", "year": 2020, "authors": [{"name": "Author"}]}]}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)

    resp = client.post('/find_paper', json={"title": "Test Title Waterfall"})
    assert resp.status_code == 200
    data = resp.json
    # It should fallback to Stage 3 because Stage 2 result is blocked
    assert data["status"] == "not_found"

@patch('src.papertrail.services.fallback.DDGS')
@patch('src.papertrail.services.search.DDGS')
@responses.activate
def test_75_waterfall_stage_1_empty__stage_2_one(mock_search_ddgs, mock_fallback_ddgs, client):
    mock_search_ddgs.return_value.__enter__.return_value.text.return_value = [{"title": "Test Title Stage 2", "href": "https://arxiv.org/pdf/1234.pdf", "body": "Test Title Stage 2"}]
    
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": [{"title": "Test Title", "year": 2020, "authors": [{"name": "Author"}]}]}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)

    resp = client.post('/find_paper', json={"title": "Test Title Stage 2"})
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "success"
    assert data["source"] == "search"
    mock_fallback_ddgs.assert_not_called()
