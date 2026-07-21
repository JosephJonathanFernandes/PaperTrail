import pytest
import responses
from src.papertrail.api.routes import app
from src.papertrail.services.verification import run_stage_1_verification, stage_1_cache

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def clear_disk_cache():
    stage_1_cache.clear()

def test_1_no_title_no_author_no_query_string(client):
    resp = client.post('/find_paper', json={})
    assert resp.status_code == 400
    assert b"error" in resp.data

@responses.activate
def test_2_title_only_no_author(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": [{"title": "Valid Title", "year": 2020}]}, status=200, match_querystring=False)
    resp = client.post('/find_paper', json={"title": "Valid Title"})
    assert resp.status_code == 200

def test_3_author_only_no_title(client):
    resp = client.post('/find_paper', json={"author": "Valid Author"})
    assert resp.status_code == 400

def test_4_title__empty_string(client):
    resp = client.post('/find_paper', json={"title": ""})
    assert resp.status_code == 400

def test_5_title__whitespace_only(client):
    resp = client.post('/find_paper', json={"title": "   "})
    assert resp.status_code == 400

@responses.activate
def test_6_title_with_unicode_chinesearabiccyrillicdevanagari(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    resp = client.post('/find_paper', json={"title": "机器学习"})
    assert resp.status_code == 404

@responses.activate
def test_7_title_with_emoji(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    resp = client.post('/find_paper', json={"title": "Attention is all you need 🤖"})
    assert resp.status_code == 404

@responses.activate
def test_8_title_1000_characters_ocr_dump_simulation(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    resp = client.post('/find_paper', json={"title": "A" * 1500})
    assert resp.status_code == 404

@responses.activate
def test_10_title_with_html_entities_amp_39(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    resp = client.post('/find_paper', json={"title": "Title with &amp; entity"})
    assert resp.status_code == 404

@responses.activate
def test_11_title_with_raw_html_tags_scriptalert1script(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    resp = client.post('/find_paper', json={"title": "<script>alert(1)</script>"})
    assert resp.status_code == 404
    assert b"<script>" not in resp.data

@responses.activate
def test_12_title_containing_shell_metacharacters__rm_rf(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    payloads = ["$(rm -rf /)", "'; DROP TABLE papers; --", "../../../../etc/passwd", "& echo 'hacked' &"]
    for p in payloads:
        resp = client.post('/find_paper', json={"query": p})
        assert resp.status_code == 404

@responses.activate
def test_13_title_that_is_itself_a_url_httplocalhost5000admin(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    resp = client.post('/find_paper', json={"title": "http://localhost:5000/admin"})
    assert resp.status_code == 404

@responses.activate
def test_14_full_apa_citation_string_as_title_eg_smith(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    resp = client.post('/find_paper', json={"query": "Smith, J. (2020). Title. Journal, 4(2), 1-10."})
    assert resp.status_code == 404

@responses.activate
def test_15_author_field_with_multiple_delimiters_smith_j_and(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    for auth in ["Smith, J. and Doe, A.", "Smith; Doe", "Smith & Doe"]:
        resp = client.post('/find_paper', json={"title": "Title", "author": auth})
        assert resp.status_code == 404

def test_16_nonjson_body__malformed_json_in_post(client):
    resp = client.post('/find_paper', data="not json", content_type="application/json")
    assert resp.status_code in [400, 415]

def test_17_wrong_contenttype_header(client):
    resp = client.post('/find_paper', data='{"title": "x"}', content_type="text/plain")
    assert resp.status_code in [400, 415]

@responses.activate
def test_18_extra_unexpected_fields_in_payload(client):
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search", json={"data": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.openalex.org/works", json={"results": []}, status=200, match_querystring=False)
    responses.add(responses.GET, "https://api.crossref.org/works", json={"message": {"items": []}}, status=200, match_querystring=False)
    resp = client.post('/find_paper', json={"title": "Title", "malicious_flag": True})
    assert resp.status_code == 404
