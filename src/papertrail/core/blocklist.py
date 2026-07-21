import re

# Exact matches for speed and known weird domains
SHADOW_LIBRARY_DOMAINS = {
    'b-ok.cc', 'bookfi.net', 'annas-archive.org'
}

# Regex patterns for domains that constantly rotate TLDs
SHADOW_LIBRARY_PATTERNS = [
    re.compile(r'^sci-hub\.[a-z]+$'),
    re.compile(r'^mirror\.sci-hub\.[a-z]+$'),
    re.compile(r'^libgen\.[a-z]+$'),
    re.compile(r'^z-lib\.[a-z]+$')
]
