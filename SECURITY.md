# Security Policy

## Supported Versions
We currently support the latest `main` branch.

## Reporting a Vulnerability
If you discover a security vulnerability within PaperTrail, please send an e-mail to the maintainers instead of opening a public issue. We will review the vulnerability and release a patch as quickly as possible.

## Secure Coding Practices
- No hardcoded secrets (API keys, emails) are permitted in the source code.
- Always use URL encoding (e.g., `urllib.parse.quote`) when injecting user input into external API requests to prevent injection attacks.
- Shadow library domains are strictly filtered. Do not remove domains from `blocklist.py`.
