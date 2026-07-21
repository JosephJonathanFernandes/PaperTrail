# Contributing to PaperTrail

First off, thank you for considering contributing to PaperTrail! 

## Development Setup
1. Fork the repo and clone it locally.
2. Run `python -m venv venv && source venv/bin/activate`.
3. Run `pip install -r requirements.txt`.
4. Set up your `.env` using `.env.example`.

## Pull Request Process
1. Write tests for any new functionality in `tests/`.
2. Ensure you run `pytest tests/` and `flake8 src/` before submitting a PR.
3. Update the `CHANGELOG.md` with your changes.

## Code Standards
- We strictly follow SOLID principles.
- Use type hints wherever possible.
- Never hardcode credentials.
