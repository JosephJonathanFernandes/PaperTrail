# PaperTrail Architecture

The system is a modular Python backend separated into distinct packages to enforce separation of concerns.

## Directory Structure
- `src/papertrail/api`: Presentation layer. Contains the Flask application and routes.
- `src/papertrail/services`: Business logic layer.
  - `verification.py`: Stage 1. CrossRef and OpenAlex integration.
  - `search.py`: Stage 2. Web search fallback using DuckDuckGo.
  - `fallback.py`: Stage 3. Discovery of ResearchGate/Contact links.
- `src/papertrail/core`: Domain rules.
  - `scoring.py`: Scoring algorithm for PDF candidates.
  - `blocklist.py`: Static definitions of banned shadow library domains.
- `src/papertrail/config`: Environment management (`settings.py`).

## Data Flow
1. API receives POST request with `title`/`author`.
2. **Stage 1** queries authoritative APIs. Returns early if an Open Access PDF is found.
3. **Stage 2** executes web searches and scores candidates. It actively filters against the shadow library blocklist.
4. **Stage 3** provides manual request links if no PDF is found.
