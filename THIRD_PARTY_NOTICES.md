# Third-Party Notices

MatchMind uses the open-source software below. Each package keeps its own license; only packages
on the Adopt list in `docs/research/open-source-review.md` may be added. Runtime licenses are
checked in CI by `scripts/check_licenses.py`.

## Runtime dependencies
| Package | License | Use |
|---|---|---|
| pydantic, pydantic-core | MIT | Data models and validation |
| pydantic-settings | MIT | Configuration from environment |
| python-dotenv | BSD-3-Clause | `.env` loading (via pydantic-settings) |
| annotated-types, typing-inspection | MIT | pydantic support |
| typing-extensions | PSF-2.0 | Typing backports |
| numpy | BSD-3-Clause | Random generation and numerics |
| pyarrow | Apache-2.0 | Parquet files for events and tracking |

## Development-only tools (not shipped)
pytest (MIT), pytest-asyncio (Apache-2.0), hypothesis (MPL-2.0), ruff (MIT), mypy (MIT), pip-licenses (MIT).

## Vendored or adapted code
Vendored code keeps its original license header.

| Code | License | Where | Use |
|---|---|---|---|
| Friends of Tracking `Metrica_PitchControl.py` (Laurie Shaw, LaurieOnTracking), Copyright (c) 2021 Friends-of-Tracking-Data-FoTD | MIT | `tests/reference/metrica_pitch_control.py` (verbatim, test-only) | Reference for the pitch control parity test |
| The same model (Spearman 2018), re-implemented and vectorized | MIT (credited) | `src/matchmind/stats/pitch_control.py` | Pitch control surfaces |
