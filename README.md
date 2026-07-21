# PaperTrail 📚

![CI Pipeline](https://github.com/yourusername/papertrail/actions/workflows/ci.yml/badge.svg)
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
   git clone https://github.com/yourusername/papertrail.git
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

## Contributing
We welcome PRs! Please read our [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to submit code.

## License
MIT License
