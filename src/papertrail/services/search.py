from src.papertrail.core.scoring import score_candidate
import requests
import re
import time
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
import re
from urllib.parse import urlparse

# Using duckduckgo_search for prototyping without API keys.
# In production, this can be swapped with SerpAPI, Google Custom Search, or Bing.
try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

def perform_search(query: str, retries: int = 3, backoff: int = 2) -> list:
    """
    Performs a web search using DuckDuckGo with retry and backoff logic.
    Returns a list of dicts: [{'url': '...', 'title': '...', 'snippet': '...'}]
    """
    if not DDGS:
        logger.warning("duckduckgo_search is not installed.")
        return []
    
    for attempt in range(retries):
        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=5):
                    results.append({
                        "url": r.get("href"),
                        "title": r.get("title", ""),
                        "snippet": r.get("body", "")
                    })
            return results
        except Exception as e:
            logger.warning(f"Search attempt {attempt + 1} failed for '{query}': {e}")
            time.sleep(backoff * (attempt + 1))
            
    return []

def extract_linkedin_outbound_links(snippet: str) -> list:
    """
    Extracts URLs from LinkedIn post snippets.
    Wrapped in try/except to handle parsing fragility gracefully.
    """
    try:
        url_pattern = re.compile(r'(https?://[^\s]+)')
        urls = url_pattern.findall(snippet)
        return urls
    except Exception as e:
        logger.warning(f"Failed to extract LinkedIn links: {e}")
        return []

def run_stage_2_search(metadata: dict) -> list:
    """
    Handles web search fallbacks via search APIs and extracts safe outbound links.
    """
    title = metadata.get("title", "")
    author_str = metadata.get("author", "")
    
    if not title:
        return []
        
    # Try to extract the last name of the first author for better search queries
    author_lastname = ""
    if author_str:
        # naive extraction: split by space and take the last word
        # In a real app, use a name parsing library
        author_lastname = author_str.split(',')[0].split(' ')[-1]

    queries = [
        f'"{title}" {author_lastname} filetype:pdf',
        f'"{title}" {author_lastname} site:researchgate.net',
        f'"{title}" {author_lastname} site:linkedin.com'
    ]
    
    candidates = []
    
    for q in queries:
        search_results = perform_search(q)
        for res in search_results:
            url = res['url']
            extracted_title = res['title']
            snippet = res['snippet']
            
            # Special handling for LinkedIn
            if "linkedin.com" in url.lower():
                outbound_urls = extract_linkedin_outbound_links(snippet)
                for out_url in outbound_urls:
                    score = score_candidate(
                        url=out_url, 
                        title=title, 
                        author_lastname=author_lastname,
                        extracted_title=extracted_title,
                        extracted_text=snippet
                    )
                    if score > 0:
                        candidates.append({
                            "url": out_url,
                            "score": score,
                            "source_query": q,
                            "original_source": "linkedin"
                        })
                    else:
                        logger.debug(f"Candidate rejected (score={score}): {out_url}")
            else:
                score = score_candidate(
                    url=url, 
                    title=title, 
                    author_lastname=author_lastname,
                    extracted_title=extracted_title,
                    extracted_text=snippet
                )
                if score > 0:
                    candidates.append({
                        "url": url,
                        "score": score,
                        "source_query": q,
                        "original_source": "search"
                    })
                else:
                    logger.debug(f"Candidate rejected (score={score}): {url}")
                    
    # Deduplicate by URL
    seen_urls = set()
    unique_candidates = []
    for c in candidates:
        if c['url'] not in seen_urls:
            seen_urls.add(c['url'])
            unique_candidates.append(c)
            
    # Sort by score descending
    unique_candidates.sort(key=lambda x: x['score'], reverse=True)
    
    return unique_candidates
