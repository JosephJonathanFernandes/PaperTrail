import re
from urllib.parse import urlparse
from rapidfuzz import fuzz
from src.papertrail.core.blocklist import SHADOW_LIBRARY_DOMAINS, SHADOW_LIBRARY_PATTERNS

def is_shadow_library(url: str) -> bool:
    """
    Checks if a given URL belongs to a known shadow library domain.
    """
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
            
        parts = domain.split('.')
        # Check exact domain and parent domains (e.g., mirror.sci-hub.se -> sci-hub.se)
        for i in range(len(parts) - 1):
            sub_domain = '.'.join(parts[i:])
            if sub_domain in SHADOW_LIBRARY_DOMAINS:
                return True
            for pattern in SHADOW_LIBRARY_PATTERNS:
                if pattern.match(sub_domain):
                    return True
        return False
    except Exception:
        # If URL parsing fails, fail-safe by blocking it
        return True

def score_candidate(url: str, title: str, author_lastname: str, extracted_title: str = "", extracted_text: str = "") -> int:
    """
    Scores a web search result candidate for legitimacy and relevance.
    Returns -1 if the URL is a shadow library.
    """
    if is_shadow_library(url):
        return -1  # HARD EXCLUDE
        
    score = 0
    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        return -1
        
    # +high (50): .edu/.ac.uk/institutional domain, arxiv.org, biorxiv.org, ssrn.com, osf.io
    high_value_domains = ['arxiv.org', 'biorxiv.org', 'ssrn.com', 'osf.io']
    if any(domain.endswith(d) for d in high_value_domains) or domain.endswith('.edu') or domain.endswith('.ac.uk'):
        score += 50
        
    # +medium (25): researchgate.net, academia.edu, author's personal site
    medium_value_domains = ['researchgate.net', 'academia.edu']
    if any(domain.endswith(d) for d in medium_value_domains):
        score += 25
        
    # +medium (25): fuzzy title match >90% (using RapidFuzz)
    if extracted_title:
        title_match_ratio = fuzz.token_sort_ratio(title.lower(), extracted_title.lower())
        if title_match_ratio > 90:
            score += 25
            
    # +bonus (15): author name present on page/metadata
    if extracted_text and author_lastname.lower() in extracted_text.lower():
        score += 15
        
    return score
