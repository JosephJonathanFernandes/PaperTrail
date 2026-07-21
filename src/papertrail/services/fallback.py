try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

def get_researchgate_link(title: str, author_lastname: str) -> str:
    """
    Searches for the specific paper's ResearchGate publication page, 
    which usually features a 'Request full-text' button.
    """
    if not DDGS or not title:
        return None
    query = f'"{title}" {author_lastname} site:researchgate.net'
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=3):
                url = r.get("href", "")
                if "researchgate.net/publication/" in url:
                    return url
    except Exception as e:
        print(f"RG Fallback Search error: {e}")
    return None

def get_author_contact_page(author: str) -> str:
    """
    Attempts to find a faculty or contact page for the author.
    """
    if not DDGS or not author:
        return None
        
    # A generic search for the author's faculty/contact page on academic domains
    query = f'"{author}" faculty OR contact OR email site:.edu OR site:.ac.uk'
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=3):
                # Return the first highly relevant result
                return r.get("href")
    except Exception as e:
        print(f"Author Search error: {e}")
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
