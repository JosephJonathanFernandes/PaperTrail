import pytest
import responses
from src.papertrail.services.verification import extract_identifiers, run_stage_1_verification, stage_1_cache

@pytest.fixture(autouse=True)
def clear_disk_cache():
    stage_1_cache.clear()

def test_extract_identifiers_arxiv():
    query = "Jimmy Lei Ba, Jamie Ryan Kiros, and Geoffrey E Hinton. Layer normalization. arXiv preprint arXiv:1607.06450, 2016."
    ids = extract_identifiers(query)
    assert ids.get("arxiv") == "1607.06450"

def test_extract_identifiers_arxiv_versioned():
    query = "Attention is all you need. arXiv:1706.03762v5"
    ids = extract_identifiers(query)
    assert ids.get("arxiv") == "1706.03762v5"

def test_extract_identifiers_doi():
    query = "Smith et al. Deep Learning. https://doi.org/10.1038/nature14539."
    ids = extract_identifiers(query)
    assert ids.get("doi") == "10.1038/nature14539"

def test_extract_identifiers_empty():
    assert extract_identifiers("") == {}
    assert extract_identifiers("Just a random string with no IDs") == {}

@responses.activate
def test_run_stage_1_semantic_scholar_success():
    """Test that Semantic Scholar is queried first and returns data correctly."""
    query = "Attention is all you need"
    
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/search?query=Attention%20is%20all%20you%20need&limit=1&fields=title,authors,year,externalIds,openAccessPdf",
        json={
            "data": [{
                "title": "Attention Is All You Need",
                "year": 2017,
                "externalIds": {"DOI": "10.5555/3295222.3295349"},
                "authors": [{"name": "Ashish Vaswani"}],
                "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762.pdf"}
            }]
        },
        status=200
    )
    
    result = run_stage_1_verification(query=query)
    
    assert result["verified"] is True
    assert result["metadata"]["title"] == "Attention Is All You Need"
    assert result["open_access_pdf"] == "https://arxiv.org/pdf/1706.03762.pdf"

@responses.activate
def test_run_stage_1_semantic_scholar_429_fallback_to_openalex():
    """Test that if Semantic Scholar returns 429 (Rate Limit), it falls back to OpenAlex."""
    query = "Attention is all you need"
    
    # Semantic Scholar returns 429
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/search?query=Attention%20is%20all%20you%20need&limit=1&fields=title,authors,year,externalIds,openAccessPdf",
        json={"message": "Too Many Requests"},
        status=429
    )
    
    # OpenAlex returns success
    responses.add(
        responses.GET,
        "https://api.openalex.org/works?search=Attention%20is%20all%20you%20need&per-page=1",
        json={
            "results": [{
                "title": "Attention Is All You Need (OpenAlex)",
                "doi": "https://doi.org/10.1234/5678",
                "publication_year": 2017,
                "authorships": [{"author": {"display_name": "Ashish Vaswani"}}],
                "open_access": {"is_oa": True, "oa_url": "https://example.com/paper.pdf"}
            }]
        },
        status=200
    )
    
    result = run_stage_1_verification(query=query)
    
    assert result["verified"] is True
    assert result["metadata"]["title"] == "Attention Is All You Need (OpenAlex)"
    assert result["open_access_pdf"] == "https://example.com/paper.pdf"

@responses.activate
def test_run_stage_1_arxiv_id_extraction_bypass():
    """Test that if an arXiv ID is in the query, it bypasses S2/OpenAlex entirely and uses arXiv API."""
    query = "Layer normalization. arXiv:1607.06450"
    
    xml_response = '''<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Layer Normalization</title>
        <published>2016-07-21T19:57:52Z</published>
        <author><name>Jimmy Lei Ba</name></author>
        <link title="pdf" href="http://arxiv.org/pdf/1607.06450v1" rel="related" type="application/pdf"/>
      </entry>
    </feed>
    '''
    
    responses.add(
        responses.GET,
        "http://export.arxiv.org/api/query?id_list=1607.06450",
        body=xml_response,
        status=200
    )
    
    result = run_stage_1_verification(query=query)
    
    assert result["verified"] is True
    assert result["metadata"]["title"] == "Layer Normalization"
    assert result["open_access_pdf"] == "http://arxiv.org/pdf/1607.06450v1"
    
    # Verify Semantic Scholar and OpenAlex were NOT called (because len(responses.calls) == 1)
    assert len(responses.calls) == 1
    assert "export.arxiv.org" in responses.calls[0].request.url
