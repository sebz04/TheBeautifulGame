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
| SQLAlchemy | MIT | Stats store (SQLite, Azure SQL) |
| mcp (Model Context Protocol Python SDK) | MIT | MCP stats server |
| agent-framework-core, agent-framework-foundry, agent-framework-openai | MIT | Agent runtime and the Foundry chat client |
| azure-identity, azure-ai-projects, azure-core | MIT | Keyless Azure sign-in and the Foundry project client |
| azure-monitor-opentelemetry-exporter, opentelemetry-api, opentelemetry-sdk | MIT, Apache-2.0 | Traces to Application Insights |
| regex | Apache-2.0 AND CNRI-Python | Text handling (via Agent Framework) |
| FastAPI, Starlette | MIT, BSD-3-Clause | The API and the site server |
| uvicorn | BSD-3-Clause | ASGI server |
| sse-starlette | BSD-3-Clause | Server-sent events for the live replay |
| azure-storage-blob (extra `azure`) | MIT | Tracking Parquet in Blob Storage |
| pyodbc (extra `azure`) | MIT | Azure SQL connections |

The container image also installs the Microsoft ODBC Driver 18 for SQL Server (`msodbcsql18`) from
Microsoft's package repository, under Microsoft's own license terms (accepted at build time with
`ACCEPT_EULA=Y`). It is not redistributed in this repository.

## Website (shipped in the browser bundle)
| Package | License | Use |
|---|---|---|
| React, React DOM | MIT | The site |
| react-router-dom | MIT | Pages |
| Zustand | MIT | App state, including the live stream |
| visx (`@visx/curve`, `@visx/scale`, `@visx/shape`) | MIT | Momentum chart |
| Big Shoulders Display, Schibsted Grotesk (Google Fonts) | SIL OFL 1.1 | Typefaces, loaded from Google Fonts |

## Development-only tools (not shipped)
- Python: pytest (MIT), pytest-asyncio (Apache-2.0), hypothesis (MPL-2.0), ruff (MIT), mypy (MIT),
  pip-licenses (MIT), floodlight (MIT; realism cross-check), agent-framework-devui (MIT; local agent UI).
- Website build and tests: Vite and @vitejs/plugin-react (MIT), TypeScript (Apache-2.0), Tailwind CSS,
  PostCSS and Autoprefixer (MIT), Vitest (MIT), Testing Library (`dom`, `react`, `jest-dom`,
  `user-event`; MIT), jsdom (MIT), Playwright (Apache-2.0), @axe-core/playwright (MPL-2.0).

## Vendored or adapted code
Vendored code keeps its original license header.

| Code | License | Where | Use |
|---|---|---|---|
| Friends of Tracking `Metrica_PitchControl.py` (Laurie Shaw, LaurieOnTracking), Copyright (c) 2021 Friends-of-Tracking-Data-FoTD | MIT | `tests/reference/metrica_pitch_control.py` (verbatim, test-only) | Reference for the pitch control parity test |
| The same model (Spearman 2018), re-implemented and vectorized | MIT (credited) | `src/matchmind/stats/pitch_control.py` | Pitch control surfaces |
