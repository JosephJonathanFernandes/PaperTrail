# PaperTrail 📚

![CI Pipeline](https://github.com/JosephJonathanFernandes/PaperTrail/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

**PaperTrail** is an enterprise-grade open-source backend for verifying scholarly citations, locating legal open-access copies of papers, and combating the spread of hallucinated references and shadow libraries.

## Problem Statement
AI agents and researchers often struggle with hallucinated citations or hit paywalls. Existing tools either scrape paywalls or rely on shadow libraries (which pose legal and security risks). PaperTrail solves this by strictly querying verified metadata APIs and legal open-access databases.

## Key Features
- **Citation Verification**: Cross-references citations against CrossRef and OpenAlex.
- **Open-Access Discovery**: Automatically resolves DOIs to legal PDFs via Unpaywall and arXiv.
- **Secure Fallbacks**: When APIs fail, performs targeted web searches while strictly filtering out a hardcoded blocklist of shadow libraries (e.g., Sci-Hub, LibGen).
- **Alternative Access**: Discovers ResearchGate 'Request full-text' links and author faculty pages when no free PDF exists.

## Architecture & Tech Stack
Built with modularity and extensibility in mind.
- **Language**: Python 3.10+
- **Framework**: Flask (API Layer)
- **Search**: DuckDuckGo (prototyping) / SerpAPI (production ready)
- **Matching**: RapidFuzz (fuzzy title matching)

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for a detailed system breakdown.

## Quickstart

### Prerequisites
- Python 3.10+
- `pip`

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/JosephJonathanFernandes/PaperTrail.git
   cd papertrail
   ```
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env and provide your UNPAYWALL_EMAIL
   ```

### Running the API
```bash
# Ensure you are running from the repository root so the src module is found
export PYTHONPATH=.
python -m src.papertrail.api.routes
```
Send a POST request to `http://localhost:5000/find_paper`:
```json
{
  "title": "Attention Is All You Need",
  "author": "Vaswani"
}
```

## Security
PaperTrail is built securely by default. It uses strict domain filtering and environment-based configuration. Please see our [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

Key security properties:
- **SSRF protected**: `resolve_redirect()` checks all outbound URLs against private IP ranges (127.x, 10.x, 172.16.x, 192.168.x, 169.254.x) before and after following redirects.
- **Shadow library blocklist**: Hard-coded list of domains (Sci-Hub, LibGen, Z-Library, Anna's Archive) is never weakened.
- **CORS fail-closed**: If `CHROME_EXTENSION_ID` is not set, all cross-origin requests are rejected.

## Known Limitations

These are honestly documented gaps — things that don't fully work yet or have known reliability limits:

### Retraction Detection
Retraction data is only checked via **OpenAlex DOI lookup** (`is_retracted` field). OpenAlex sources this from RetractionWatch, which has good coverage but is not exhaustive. **Semantic Scholar's retraction field is not queried** — it requires an authenticated API key, which is not provided by default. Papers retracted after OpenAlex's last sync may not be flagged. **Do not rely on PaperTrail as the sole retraction check for critical decisions.**

### Open-Access Coverage
PaperTrail queries Unpaywall, arXiv, and CORE for legal PDFs. **PMC (PubMed Central) and DOAJ are not currently integrated** — biomedical papers may have lower OA hit rates as a result. CORE integration is present but works at reduced rate limits without a `CORE_API_KEY`.

### Author Matching
Author matching uses last-name normalization (handles "A. Vaswani" = "Ashish Vaswani"). However, **names with diacritics** (e.g. "Müller" vs "Muller"), **CJK names**, and **ambiguous single-name cases** may produce false author-mismatch flags.

### Chrome Extension — PDF Viewer
The extension **does not work inside Chrome's native PDF viewer** (`chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai`). Content scripts cannot inject into the sandboxed PDF viewer context. To verify a citation from a PDF, copy the text and verify it on any regular webpage.

### DuckDuckGo Rate Limits
Stage 2 web search and Stage 3 fallback use DuckDuckGo with no API key. DDG may throttle or block requests under heavy use. Each call has an 8-second hard timeout, but sustained bursts will hit rate limits and return empty results. Consider replacing with SerpAPI or Google Custom Search for production use.

### Rate Limiting Storage
The Flask-Limiter rate limit uses **in-memory storage** and resets on server restart. It is not shared across multiple workers (e.g. gunicorn with multiple processes). Use Redis storage backend for multi-worker deployments.

## Contributing
We welcome PRs! Please read our [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to submit code.

## License
MIT License
