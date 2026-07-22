from src.papertrail.core.scoring import score_candidate
import requests
import re
import time
import ipaddress
import logging
import threading
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Using duckduckgo_search for prototyping without API keys.
# In production, this can be swapped with SerpAPI, Google Custom Search, or Bing.
try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

def _ddg_search_with_timeout(query: str, timeout: int = 8) -> list:
    """
    Runs a single DuckDuckGo search call inside a thread with a hard timeout.
    Returns results list or raises TimeoutError if the call hangs.
    """
    results = []
    exc_box = [None]

    def _run():
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=5):
                    results.append({
                        "url": r.get("href"),
                        "title": r.get("title", ""),
                        "snippet": r.get("body", "")
                    })
        except Exception as e:
            exc_box[0] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"DDG search timed out after {timeout}s for query: {query}")
    if exc_box[0]:
        raise exc_box[0]
    return results

def perform_search(query: str, retries: int = 3, backoff: int = 2) -> list:
    """
    Performs a web search using DuckDuckGo with retry and backoff logic.
    Returns a list of dicts: [{'url': '...', 'title': '...', 'snippet': '...'}]
    Each individual DDG call has an 8-second hard timeout to prevent hangs.
    """
    if not DDGS:
        logger.warning("duckduckgo_search is not installed.")
        return []
    
    for attempt in range(retries):
        try:
            return _ddg_search_with_timeout(query, timeout=8)
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

# Private/internal IP ranges that must never be fetched (SSRF protection)
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / AWS metadata
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique-local
]

def _is_private_url(url: str) -> bool:
    """
    Returns True if a URL resolves to a private/internal IP range.
    Checks BEFORE making the request to block SSRF.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return True  # Fail closed on unparseable hosts
        # Block by hostname pattern (e.g. metadata.google.internal)
        internal_hostnames = {
            "localhost", "metadata.google.internal",
            "169.254.169.254", "instance-data"
        }
        if host.lower() in internal_hostnames:
            return True
        # Attempt to parse as IP address
        try:
            addr = ipaddress.ip_address(host)
            return any(addr in net for net in _PRIVATE_NETWORKS)
        except ValueError:
            pass  # Not an IP address — hostname, allow through
        return False
    except Exception:
        return True  # Fail closed

def resolve_redirect(url: str, timeout: int = 5) -> str:
    """
    Resolves shortlinks or sneaky redirects to their final destination.
    SSRF-safe: blocks private IP ranges before any request is made,
    and re-validates the final URL after following all redirects.
    """
    if _is_private_url(url):
        logger.warning(f"SSRF blocked (pre-request): {url}")
        return url  # Return the original URL unchanged; caller's score_candidate will reject it
    try:
        res = requests.head(url, allow_redirects=True, timeout=timeout)
        # Some servers block HEAD requests, fallback to streaming GET
        if res.status_code >= 400:
            res = requests.get(url, allow_redirects=True, stream=True, timeout=timeout)
            res.close()
        final_url = res.url
        # Re-validate the FINAL resolved URL after following all redirects
        if _is_private_url(final_url):
            logger.warning(f"SSRF blocked (post-redirect): {url} -> {final_url}")
            return url  # Discard the redirect chain, return original
        return final_url
    except requests.RequestException as e:
        logger.debug(f"Redirect resolution failed for {url}: {e}")
        return url

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
            url = res.get('url')
            if not url:
                continue
                
            extracted_title = res['title']
            snippet = res['snippet']
            
            # Special handling for LinkedIn
            if "linkedin.com" in url.lower():
                outbound_urls = extract_linkedin_outbound_links(snippet)
                for out_url in outbound_urls:
                    final_url = resolve_redirect(out_url)
                    score = score_candidate(
                        url=final_url, 
                        title=title, 
                        author_lastname=author_lastname,
                        extracted_title=extracted_title,
                        extracted_text=snippet
                    )
                    if score > 0:
                        candidates.append({
                            "url": final_url,
                            "score": score,
                            "source_query": q,
                            "original_source": "linkedin"
                        })
                    else:
                        logger.debug(f"Candidate rejected (score={score}): {final_url}")
            else:
                final_url = resolve_redirect(url)
                score = score_candidate(
                    url=final_url, 
                    title=title, 
                    author_lastname=author_lastname,
                    extracted_title=extracted_title,
                    extracted_text=snippet
                )
                if score > 0:
                    candidates.append({
                        "url": final_url,
                        "score": score,
                        "source_query": q,
                        "original_source": "search"
                    })
                else:
                    logger.debug(f"Candidate rejected (score={score}): {final_url}")
                    
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
