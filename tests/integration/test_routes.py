import pytest
import json
from src.papertrail.api.routes import app
import responses

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_find_paper_missing_query(client):
    """Test that a missing query returns a 400 Bad Request."""
    response = client.post('/find_paper', json={})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert "error" in data

@responses.activate
def test_find_paper_success(client):
    """Test a successful paper finding request."""
    query = "Layer normalization. arXiv:1607.06450"
    
    # Mock arXiv API
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
    
    response = client.post('/find_paper', json={"query": query})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert data["source"] == "api"
    assert data["pdf_url"] == "http://arxiv.org/pdf/1607.06450v1"
    assert data["metadata"]["title"] == "Layer Normalization"

def test_find_papers_batch_missing_query(client):
    """Test that missing citations array returns a 400."""
    response = client.post('/find_papers_batch', json={})
    assert response.status_code == 400

@responses.activate
def test_find_papers_batch_success(client):
    """Test batch finding."""
    citations = ["Layer normalization. arXiv:1607.06450"]
    
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
    
    response = client.post('/find_papers_batch', json={"citations": citations})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data["results"]) == 1
    assert data["results"][0]["status"] == "success"
    
@responses.activate
def test_export_batch_csv(client):
    """Test CSV export endpoint."""
    citations = ["Layer normalization. arXiv:1607.06450"]
    
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
    
    response = client.post('/export_batch_csv', json={"citations": citations})
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    csv_content = response.data.decode('utf-8')
    assert "Citation,Status,Confidence Tier,Confidence Score,Flags,PDF Link" in csv_content
    assert "Layer normalization" in csv_content
    assert "Found" in csv_content
    assert "HIGH" in csv_content
    assert "100" in csv_content
