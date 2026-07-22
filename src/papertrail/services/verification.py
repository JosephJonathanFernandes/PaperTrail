import re
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
CORE_API_KEY = Config.CORE_API_KEY

# Configure a resilient HTTP session with retries for transient network errors
session = requests.Session()
retry = Retry(
    total=1,
    backoff_factor=0.1,
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
        response = session.get(url, timeout=3)
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
        response = session.get(url, timeout=3)
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
        response = session.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            if results:
                return results[0]
    except Exception as e:
        print(f"OpenAlex error: {e}")
    return None

def check_openalex_by_doi(doi: str) -> dict:
    url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    try:
        response = session.get(url, timeout=3)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"OpenAlex DOI error: {e}")
    return None

def check_pmc_retraction(doi: str) -> bool:
    """Checks if a DOI is marked as retracted in Europe PMC."""
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=ext_id:{urllib.parse.quote(doi)}+AND+RETR:Y&format=json"
    try:
        response = session.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get('hitCount', 0) > 0:
                return True
    except Exception as e:
        print(f"PMC Retraction error: {e}")
    return False

def check_doaj(doi: str) -> str:
    """Checks DOAJ for Open Access fulltext link."""
    url = f"https://doaj.org/api/v3/search/articles/doi:{urllib.parse.quote(doi)}"
    try:
        response = session.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            if results:
                bibjson = results[0].get('bibjson', {})
                links = bibjson.get('link', [])
                for link in links:
                    if link.get('type') == 'fulltext':
                        return link.get('url')
    except Exception as e:
        print(f"DOAJ error: {e}")
    return None

def check_unpaywall(doi: str) -> str:
    url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
    try:
        response = session.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get('is_oa'):
                best_oa_location = data.get('best_oa_location')
                if best_oa_location and best_oa_location.get('url_for_pdf'):
                    return best_oa_location['url_for_pdf']
                # Also try url (HTML landing) if no direct pdf url available
                if best_oa_location and best_oa_location.get('url'):
                    return best_oa_location['url']
    except Exception as e:
        print(f"Unpaywall error: {e}")
    return None

def check_core(title: str, doi: str = None) -> str:
    """
    Queries the CORE API (https://core.ac.uk/services/api) for open-access PDFs.
    CORE aggregates 230M+ papers from repositories that Unpaywall sometimes misses.
    Works without an API key (rate-limited) or with CORE_API_KEY for higher limits.
    Returns a direct PDF URL or None.
    """
    headers = {}
    if CORE_API_KEY:
        headers["Authorization"] = f"Bearer {CORE_API_KEY}"

    # Prefer DOI lookup — most precise
    if doi:
        url = f"https://api.core.ac.uk/v3/works?q=doi:{urllib.parse.quote(doi)}&limit=1"
        try:
            response = session.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                if results:
                    pdf = results[0].get('downloadUrl') or results[0].get('fullTextIdentifier')
                    if pdf and pdf.startswith('http'):
                        return pdf
        except Exception as e:
            print(f"CORE DOI lookup error: {e}")

    # Fall back to title search
    if title:
        url = f"https://api.core.ac.uk/v3/works?q={urllib.parse.quote(title)}&limit=1"
        try:
            response = session.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                if results:
                    pdf = results[0].get('downloadUrl') or results[0].get('fullTextIdentifier')
                    if pdf and pdf.startswith('http'):
                        return pdf
        except Exception as e:
            print(f"CORE title search error: {e}")
    return None

def check_arxiv(title: str, author: str) -> str:
    query = f"ti:\"{title}\""
    if author:
        query += f" AND au:\"{author}\""
    url = f"http://export.arxiv.org/api/query?search_query={urllib.parse.quote(query)}&max_results=1"
    try:
        response = session.get(url, timeout=3)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                for link in entry.findall('{http://www.w3.org/2005/Atom}link'):
                    if link.attrib.get('title') == 'pdf':
                        return link.attrib.get('href')
    except Exception as e:
        print(f"arXiv error: {e}")
    return None

def check_arxiv_by_id(arxiv_id: str) -> dict:
    url = f"http://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}"
    try:
        response = session.get(url, timeout=3)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            entry = root.find('{http://www.w3.org/2005/Atom}entry')
            if entry is not None:
                title = entry.find('{http://www.w3.org/2005/Atom}title').text.replace('\\n', ' ')
                published = entry.find('{http://www.w3.org/2005/Atom}published').text
                year = published[:4] if published else None
                authors = [{"family": a.find('{http://www.w3.org/2005/Atom}name').text} for a in entry.findall('{http://www.w3.org/2005/Atom}author')]
                
                pdf_url = None
                for link in entry.findall('{http://www.w3.org/2005/Atom}link'):
                    if link.attrib.get('title') == 'pdf':
                        pdf_url = link.attrib.get('href')
                        break
                        
                return {
                    "title": title,
                    "year": int(year) if year else None,
                    "authors": authors,
                    "open_access_pdf": pdf_url,
                    "doi": f"10.48550/arXiv.{arxiv_id}"
                }
    except Exception as e:
        print(f"arXiv ID error: {e}")
    return None

def extract_identifiers(query: str) -> dict:
    """Extracts explicit identifiers like arXiv IDs and DOIs from messy citation strings."""
    ids = {}
    if not query:
        return ids
        
    arxiv_match = re.search(r'(?:arxiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)', query.lower())
    if arxiv_match:
        ids['arxiv'] = arxiv_match.group(1)
        
    doi_match = re.search(r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', query, re.I)
    if doi_match:
        ids['doi'] = doi_match.group(1).rstrip('.,;:')
        
    return ids

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
        "authors": [],
        "is_retracted": False
    }
    pdf_url = None
    
    # 0. Check if the query contains an explicit identifier
    ids = extract_identifiers(f"{query or ''} {title or ''}".strip())
    if "arxiv" in ids:
        arxiv_res = check_arxiv_by_id(ids["arxiv"])
        if arxiv_res:
            verified = True
            metadata["title"] = arxiv_res["title"]
            metadata["year"] = arxiv_res["year"]
            metadata["authors"] = arxiv_res["authors"]
            metadata["doi"] = arxiv_res["doi"]
            pdf_url = arxiv_res["open_access_pdf"]
            
    if not verified and "doi" in ids:
        oa_doi_res = check_openalex_by_doi(ids["doi"])
        if oa_doi_res:
            verified = True
            metadata["title"] = oa_doi_res.get("title", metadata["title"])
            metadata["doi"] = ids["doi"]
            metadata["year"] = oa_doi_res.get("publication_year")
            metadata["authors"] = [a.get("author", {}) for a in oa_doi_res.get("authorships", [])]
            if oa_doi_res.get("is_retracted"):
                metadata["is_retracted"] = True
            
            oa = oa_doi_res.get("open_access", {})
            if oa.get("is_oa") and oa.get("oa_url") and oa["oa_url"].endswith(".pdf"):
                pdf_url = oa["oa_url"]
                
    # 1. Search Semantic Scholar First (Excellent for CS/AI, but prone to rate limits without a key)
    s2_res = None
    if not verified:
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
            if openalex_res.get("is_retracted"):
                metadata["is_retracted"] = True
            
            oa = openalex_res.get("open_access", {})
            if not pdf_url and oa.get("is_oa") and oa.get("oa_url"):
                if oa["oa_url"].endswith(".pdf"):
                    pdf_url = oa["oa_url"]
                
    # 3. Search CrossRef if OpenAlex didn't yield a DOI
    if not verified or not metadata["doi"]:
        crossref_res = search_crossref(metadata["title"] or title or query, author)
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

    # 5. Check CORE — aggregates repositories Unpaywall sometimes misses
    if not pdf_url:
        core_pdf = check_core(metadata["title"] or title, doi=metadata.get("doi"))
        if core_pdf:
            pdf_url = core_pdf

    # 5.5 Check DOAJ if we have a DOI but no PDF URL yet
    if metadata["doi"] and not pdf_url:
        doaj_pdf = check_doaj(metadata["doi"])
        if doaj_pdf:
            pdf_url = doaj_pdf

    # 6. Fallback check for arXiv directly
    if verified and not pdf_url and metadata["title"]:
        arxiv_pdf = check_arxiv(metadata["title"], metadata["author"])
        if arxiv_pdf:
            pdf_url = arxiv_pdf
            
    # 7. Final Safety Check: Retractions via PMC
    if verified and metadata["doi"] and not metadata.get("is_retracted"):
        if check_pmc_retraction(metadata["doi"]):
            metadata["is_retracted"] = True

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
