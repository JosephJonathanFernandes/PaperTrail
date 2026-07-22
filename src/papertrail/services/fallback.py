try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

import logging
from src.papertrail.services.search import _ddg_search_with_timeout

logger = logging.getLogger(__name__)

def get_researchgate_link(title: str, author_lastname: str) -> str:
    """
    Searches for the specific paper's ResearchGate publication page,
    which usually features a 'Request full-text' button.
    Uses the shared DDG timeout wrapper to prevent worker hangs.
    """
    if not DDGS or not title:
        return None
    query = f'"{title}" {author_lastname} site:researchgate.net'
    try:
        results = _ddg_search_with_timeout(query, timeout=8)
        for r in results:
            url = r.get("url", "")
            if "researchgate.net/publication/" in url:
                return url
    except Exception as e:
        logger.warning(f"RG Fallback Search error: {e}")
    return None

def get_author_contact_page(author: str) -> str:
    """
    Attempts to find a faculty or contact page for the author.
    Uses the shared DDG timeout wrapper to prevent worker hangs.
    Note: Only searches publicly indexed .edu/.ac.uk pages via DuckDuckGo.
    Does NOT scrape ResearchGate or LinkedIn author profiles.
    """
    if not DDGS or not author:
        return None
        
    # A generic search for the author's faculty/contact page on academic domains
    query = f'"{author}" faculty OR contact OR email site:.edu OR site:.ac.uk'
    try:
        results = _ddg_search_with_timeout(query, timeout=8)
        if results:
            return results[0].get("url")
    except Exception as e:
        logger.warning(f"Author Search error: {e}")
    return None

def run_stage_3_fallback(metadata: dict) -> dict:
    """
    Discovers alternative legal ways to access the paper when no free PDF is available.
    """
    title = metadata.get("title", "")
    author_str = metadata.get("author", "")
    
    author_lastname = ""
    if author_str:
        author_lastname = author_str.split(',')[0].split(' ')[-1]

    rg_link = get_researchgate_link(title, author_lastname)
    author_page = get_author_contact_page(author_str)
    
    message = "No legal Open Access PDF could be found. "
    if rg_link:
        message += "You can request the full-text directly from the authors on ResearchGate. "
    else:
        message += "We recommend checking if your library provides Interlibrary Loan (ILL) access. "
        
    if author_page:
        message += "Alternatively, you may try reaching out to the author via their institutional page."

    return {
        "author_contact_page": author_page,
        "request_fulltext_link": rg_link,
        "interlibrary_loan_suggested": True,
        "message": message.strip()
    }
