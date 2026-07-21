import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib.parse
import xml.etree.ElementTree as ET
import diskcache
from src.papertrail.config.settings import Config
from src.papertrail.core.scoring import calculate_confidence

# Initialize a persistent disk cache for Stage 1 lookups (expires in 30 days)
stage_1_cache = diskcache.Cache(".cache")

# Using the email from environment configuration for Unpaywall API rate limiting
UNPAYWALL_EMAIL = Config.UNPAYWALL_EMAIL

# Configure a resilient HTTP session with retries for transient network errors
session = requests.Session()
retry = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET"]
)
adapter = HTTPAdapter(max_retries=retry)
session.mount("http://", adapter)
session.mount("https://", adapter)


def search_semantic_scholar(query: str, title: str, author: str) -> dict:
    search_str = query if query else f"{title} {author}".strip()
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(search_str)}&limit=1&fields=title,authors,year,externalIds,openAccessPdf"
    try:
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            items = data.get('data', [])
            if items:
                return items[0]
    except Exception as e:
        print(f"Semantic Scholar error: {e}")
    return None


def search_crossref(title: str, author: str) -> dict:
    query_parts = []
    if title:
        query_parts.append(f"query.bibliographic={urllib.parse.quote(title)}")
    if author:
        query_parts.append(f"query.author={urllib.parse.quote(author)}")
    
    url = f"https://api.crossref.org/works?{'&'.join(query_parts)}&rows=1"
    try:
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            items = data.get('message', {}).get('items', [])
            if items:
                return items[0]
    except Exception as e:
        print(f"CrossRef error: {e}")
    return None

def search_openalex(query: str, title: str, author: str) -> dict:
    search_str = query if query else f"{title} {author}".strip()
    url = f"https://api.openalex.org/works?search={urllib.parse.quote(search_str)}&per-page=1"
    try:
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            if results:
                return results[0]
    except Exception as e:
        print(f"OpenAlex error: {e}")
    return None

def check_unpaywall(doi: str) -> str:
    url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
    try:
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('is_oa'):
                best_oa_location = data.get('best_oa_location')
                if best_oa_location and best_oa_location.get('url_for_pdf'):
                    return best_oa_location['url_for_pdf']
    except Exception as e:
        print(f"Unpaywall error: {e}")
    return None

def check_arxiv(title: str, author: str) -> str:
    query = f"ti:\"{title}\""
    if author:
        query += f" AND au:\"{author}\""
    url = f"http://export.arxiv.org/api/query?search_query={urllib.parse.quote(query)}&max_results=1"
    try:
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                for link in entry.findall('{http://www.w3.org/2005/Atom}link'):
                    if link.attrib.get('title') == 'pdf':
                        return link.attrib.get('href')
    except Exception as e:
        print(f"arXiv error: {e}")
    return None

@stage_1_cache.memoize(expire=2592000)
def run_stage_1_verification(query: str = None, title: str = None, author: str = None) -> dict:
    """
    Queries official metadata APIs (Semantic Scholar, OpenAlex, CrossRef, Unpaywall, arXiv).
    Returns a standardized metadata object and verifies authenticity.
    """
    verified = False
    metadata = {
        "title": title or "",
        "author": author or "",
        "doi": None,
        "year": None,
        "journal": None,
        "authors": []
    }
    pdf_url = None
    
    # 1. Search Semantic Scholar First (Excellent for CS/AI, but prone to rate limits without a key)
    s2_res = search_semantic_scholar(query, title, author)
    if s2_res:
        verified = True
        metadata["title"] = s2_res.get("title", metadata["title"])
        metadata["doi"] = s2_res.get("externalIds", {}).get("DOI")
        metadata["year"] = s2_res.get("year")
        metadata["authors"] = [a for a in s2_res.get("authors", [])]
        
        if s2_res.get("openAccessPdf"):
            pdf_url = s2_res["openAccessPdf"].get("url")

    # 2. Search OpenAlex if S2 failed or didn't yield a DOI
    if not verified or not metadata["doi"]:
        openalex_res = search_openalex(query, title, author)
        if openalex_res:
            verified = True
            metadata["title"] = openalex_res.get("title", metadata["title"])
            metadata["doi"] = openalex_res.get("doi", "").replace("https://doi.org/", "") if openalex_res.get("doi") else metadata["doi"]
            if not metadata["year"]:
                metadata["year"] = openalex_res.get("publication_year")
            if not metadata["authors"]:
                metadata["authors"] = [a.get("author", {}) for a in openalex_res.get("authorships", [])]
            
            oa = openalex_res.get("open_access", {})
            if not pdf_url and oa.get("is_oa") and oa.get("oa_url"):
                if oa["oa_url"].endswith(".pdf"):
                    pdf_url = oa["oa_url"]
                
    # 3. Search CrossRef if OpenAlex didn't yield a DOI
    if not verified or not metadata["doi"]:
        crossref_res = search_crossref(metadata["title"] or title, author)
        if crossref_res:
            verified = True
            metadata["title"] = crossref_res.get("title", [metadata["title"]])[0]
            metadata["doi"] = crossref_res.get("DOI")
            if not metadata["authors"]:
                metadata["authors"] = crossref_res.get("author", [])
            
    # 4. Check Unpaywall if we have a DOI but no PDF URL yet
    if metadata["doi"] and not pdf_url:
        unpaywall_pdf = check_unpaywall(metadata["doi"])
        if unpaywall_pdf:
            pdf_url = unpaywall_pdf
            
    # 5. Fallback check for arXiv directly
    if verified and not pdf_url and metadata["title"]:
        arxiv_pdf = check_arxiv(metadata["title"], metadata["author"])
        if arxiv_pdf:
            pdf_url = arxiv_pdf
            
    if not verified:
        return {"verified": False}
        
    confidence = calculate_confidence(query, title, author, metadata)

    return {
        "verified": True,
        "confidence_score": confidence["score"],
        "confidence_tier": confidence["tier"],
        "flags": confidence["flags"],
        "metadata": metadata,
        "open_access_pdf": pdf_url,
        "source": "api"
    }
