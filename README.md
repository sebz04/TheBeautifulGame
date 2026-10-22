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

## Credits
- Pitch control follows Spearman (2018), "Beyond Expected Goals", and the Friends of Tracking implementation by Laurie Shaw ([LaurieOnTracking](https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking), MIT). Our version in `src/matchmind/stats/pitch_control.py` is vectorized and parity-tested against it. See `THIRD_PARTY_NOTICES.md`.
