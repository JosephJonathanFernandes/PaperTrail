import pytest
import responses
from unittest.mock import patch
from src.papertrail.services.verification import run_stage_1_verification, stage_1_cache
from requests.exceptions import Timeout, ConnectionError
import re
from src.papertrail.api.routes import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def clear_disk_cache():
    stage_1_cache.clear()

@responses.activate
def test_50_crossref_returns_500():
    query = "Some Title"
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", status=500, match_querystring=False)
    
    res = run_stage_1_verification(title=query)
    assert res["verified"] is False

@responses.activate
def test_51_openalex_times_out_mock_30s_hang():
    query = "Some Title"
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", body=Timeout(), match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    
    res = run_stage_1_verification(title=query)
    assert res["verified"] is False

@responses.activate
def test_52_unpaywall_returns_malformed_json():
    query = "Some Title"
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": [{"title": "Title", "externalIds": {"DOI": "10.123"}}]}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.123", body="{bad json", status=200, match_querystring=False)
    
    res = run_stage_1_verification(title=query)
    assert res["verified"] is True # Verified by Semantic Scholar, but Unpaywall failed gracefully
    assert res.get("open_access_pdf") is None

@responses.activate
def test_53_arxiv_api_returns_empty_but_valid_xmljson():
    query = "Some Title"
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": [{"title": "Title", "authors": [{"name": "A"}]}]}, status=200, match_querystring=False)
    responses.add(responses.GET, "http://export.arxiv.org/api/query", body="""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>""", status=200, match_querystring=False)
    
    res = run_stage_1_verification(title=query)
    assert res["verified"] is True
    assert res.get("open_access_pdf") is None

@patch('src.papertrail.services.fallback.DDGS')
@responses.activate
def test_54_all_external_apis_simultaneously_unreachable(mock_ddgs, client):
    mock_instance = mock_ddgs.return_value.__enter__.return_value
    mock_instance.text.return_value = []
    
    responses.add(responses.GET, re.compile(r".*api.semanticscholar.org.*"), body=ConnectionError())
    responses.add(responses.GET, re.compile(r".*api.openalex.org.*"), body=ConnectionError())
    responses.add(responses.GET, re.compile(r".*api.crossref.org.*"), body=ConnectionError())
    
    res = client.post('/find_paper', json={"title": "Network Outage Test", "author": "Test Author"})
    
    assert res.status_code == 404
    data = res.json
    assert data["status"] == "unverified"

@responses.activate
def test_55_dns_resolution_failure_for_one_upstream_api():
    query = "Some Title"
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", body=ConnectionError("Failed to resolve"), match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    
    res = run_stage_1_verification(title=query)
    assert res["verified"] is False
