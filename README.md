# TheBeautifulGame
Inside the Game Hackathon 2026 Project Led and Authored By Sebastian Zapata

**MatchMind** turns synthetic football events into explainable, verified, personalized match intelligence, built on Microsoft Foundry and Microsoft Agent Framework.

## Quick start (development)

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 automatically).

```bash
uv sync                 # install dependencies
cp .env.example .env    # optional: local configuration (never commit .env)
uv run pytest           # tests
uv run ruff check .     # lint
uv run mypy src         # type check
```

Project rules: [CONSTITUTION.md](CONSTITUTION.md) · Codebase map: [wiki/README.md](wiki/README.md)
