import re
from urllib.parse import urlparse
from rapidfuzz import fuzz
from src.papertrail.core.blocklist import SHADOW_LIBRARY_DOMAINS, SHADOW_LIBRARY_PATTERNS

def _normalize_author(name: str) -> tuple:
    """
    Normalizes an author name into (last_name, first_initial) for comparison.
    Handles formats like:
      - "Ashish Vaswani"  → ("vaswani", "a")
      - "Vaswani, A."     → ("vaswani", "a")
      - "A. Vaswani"      → ("vaswani", "a")
      - "Vaswani"         → ("vaswani", "")
    Returns (last_name_lower, first_initial_lower).
    """
    name = name.strip().rstrip('.')
    # Format: "Last, First" or "Last, F."
    if ',' in name:
        parts = [p.strip() for p in name.split(',', 1)]
        last = parts[0].lower()
        first = parts[1].strip().lstrip('.').strip() if len(parts) > 1 else ''
        initial = first[0].lower() if first else ''
        return (last, initial)
    # Format: "First Last" or "F. Last"
    tokens = name.split()
    if len(tokens) == 1:
        return (tokens[0].lower(), '')
    last = tokens[-1].lower()
    first_token = tokens[0].rstrip('.')
    initial = first_token[0].lower() if first_token else ''
    return (last, initial)

def _author_match(input_author: str, api_authors_str: str) -> bool:
    """
    Returns True if input_author plausibly matches any author in api_authors_str.
    Matching rules (in order of strictness):
      1. Direct substring match (fast path)
      2. Last-name match (sufficient for single-name queries like "Vaswani")
      3. Last-name + initial match (handles "A. Vaswani" vs "Ashish Vaswani")
    """
    inp_lower = input_author.lower()
    api_lower = api_authors_str.lower()
    # Fast path: direct substring
    if inp_lower in api_lower:
        return True
    inp_last, inp_initial = _normalize_author(input_author)
    # Match against each token-cluster in api_authors (split on comma/space)
    # Build list of candidate author names from the API string
    # The api_authors_str is a space-joined "family" field from various APIs
    for candidate in re.split(r'[,;|]+', api_authors_str):
        candidate = candidate.strip()
        if not candidate:
            continue
        cand_last, cand_initial = _normalize_author(candidate)
        if cand_last == inp_last:
            # Last name matches — if we have initials for both, check them too
            if inp_initial and cand_initial:
                if inp_initial == cand_initial:
                    return True
            else:
                # One or both sides have no initial — last name alone is sufficient
                return True
    return False

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

def calculate_confidence(input_query: str, input_title: str, input_author: str, api_metadata: dict) -> dict:
    """
    Compares the user's input against the API metadata to generate a confidence score and flags.
    """
    score = 100
    flags = []
    
    api_title = api_metadata.get("title", "")
    api_authors = " ".join([a.get("family", a.get("name", "")) for a in api_metadata.get("authors", [])])
    
    if input_title and api_title:
        title_sim = fuzz.ratio(input_title.lower(), api_title.lower())
        
        arxiv_match = re.search(r'(\d{4}\.\d{4,5})', input_title)
        if arxiv_match and api_metadata.get("doi") and arxiv_match.group(1) in api_metadata.get("doi"):
            title_sim = 100
            
        if title_sim < 95:
            score -= (100 - title_sim) * 0.5
            flags.append(f"Title mismatch ({title_sim:.1f}% similarity). Expected: '{input_title}', Found: '{api_title}'")
            
    if input_author and api_authors:
        if not _author_match(input_author, api_authors):
            score -= 20
            flags.append(f"Author mismatch. '{input_author}' not found in canonical author list.")
            
    if input_query and not input_title:
        # Broad free-text match
        api_combined = f"{api_title} {api_authors} {api_metadata.get('year', '')}"
        query_sim = fuzz.token_set_ratio(input_query.lower(), api_combined.lower())
        
        # If the user queried an arXiv ID and the API resolved it, it's a perfect match
        arxiv_match = re.search(r'(\d{4}\.\d{4,5})', input_query)
        if arxiv_match and api_metadata.get("doi") and arxiv_match.group(1) in api_metadata.get("doi"):
            query_sim = 100
            
        if query_sim < 60:
            score -= (100 - query_sim) * 0.5
            flags.append(f"Query match weak ({query_sim:.1f}%). Input may be hallucinated or heavily distorted.")
            
    score = max(0, min(100, int(score)))
    
    if score >= 90:
        tier = "HIGH"
    elif score >= 70:
        tier = "MEDIUM"
    else:
        tier = "LOW"
        
    if api_metadata.get("is_retracted"):
        score = 0
        tier = "LOW"
        flags.insert(0, "🚨 RETRACTED PAPER: This paper has been officially retracted. Do not cite.")
        
    return {
        "score": score,
        "tier": tier,
        "flags": flags
    }
