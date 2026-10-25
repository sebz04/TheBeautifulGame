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

### Build the showcase matches

```bash
uv run matchmind build --all --season   # season history once, then the 8 storylines
uv run matchmind build --scenario scenarios/comeback_red_card.toml   # one match
```

Each match is simulated, then its events, 10 Hz tracking, key moments, overlay cues, and metric snapshots go to the store (SQLite at `data/matchmind.db` and Parquet under `data/tracking/` by default; Azure SQL and Blob when configured). Rebuilding a match replaces its rows.

Timing (8-core laptop, 2026-10-25): about 47 s per match and 11 min 41 s for `--all --season`, including about 5 min for the season history. That builds 8 matches with 20–40 moments each, about 1,400 cues each, and about 93,000 metric rows each (119 MB of SQLite and 89 MB of tracking).

Project rules: [CONSTITUTION.md](CONSTITUTION.md) · Codebase map: [wiki/README.md](wiki/README.md)

## Credits
- Pitch control follows Spearman (2018), "Beyond Expected Goals", and the Friends of Tracking implementation by Laurie Shaw ([LaurieOnTracking](https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking), MIT). Our version in `src/matchmind/stats/pitch_control.py` is vectorized and parity-tested against it. See `THIRD_PARTY_NOTICES.md`.
