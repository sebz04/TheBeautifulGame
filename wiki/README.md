# MatchMind Wiki

A short, current map of the codebase. **Read this page first, then only the pages you need.** Pages describe what exists in the code *now*. Plans live in `docs/superpowers/plans/2026-10-21-matchmind.md`, and work tracking lives in `TASKS.md`.

**Last updated:** 2026-10-21 · **Latest task:** TASK-3.3 · **Code status:** scaffold, schemas, league and fixtures

## Current state
- Done: constitution, implementation plan, task breakdown, open-source review, this wiki.
- Built: uv project, settings (`src/matchmind/config.py`), CI, license gate (`scripts/check_licenses.py`), wiki check (`scripts/check_wiki.py` + `.githooks/pre-commit`), shared schemas and pitch geometry, 20-club LA league with squads and fixtures, player and club profiles, chemistry.
- Next: TASK-3.4 (origins, transfers, legends). The user is setting up Azure for Students and Foundry (TASK-16.1).
- Blockers: none for TASK-1 to TASK-15. TASK-16.2 onward needs the Foundry deployment.

## Pages
| Page | Covers | Read when |
|---|---|---|
| [architecture.md](architecture.md) | Data flow, fast and insight lanes, components and their status | Starting any cross-cutting work |
| [data-model.md](data-model.md) | Schemas, units, ID formats, DB tables | Touching schemas, store, or API payloads |
| [league.md](league.md) | Clubs, squads, latent factors, distributions, names, fixtures, profiles | Work in `src/matchmind/league` |
| [engine.md](engine.md) | Synthetic match engine levels, constants, scenarios | Work in `src/matchmind/engine` |
| [stats.md](stats.md) | xT, pitch control, pass/speed/team metrics, moments, counterfactuals | Work in `src/matchmind/stats` |
| [agents.md](agents.md) | Agents, prompts, workflow, Verifier rules, fallbacks | Work in `src/matchmind/agents` or `mcp_server` |
| [api-frontend.md](api-frontend.md) | Endpoints, SSE contract, frontend components | Work in `src/matchmind/api` or `web/` |
| [infra-ops.md](infra-ops.md) | Azure resources, env vars, commands, costs | Deploying, configuring, or debugging cloud |
| [conventions.md](conventions.md) | Commands, testing, commit and wiki rules | Before your first commit in a session |
| [decisions.md](decisions.md) | Decisions and why they were made | Before changing a design choice |
| [glossary.md](glossary.md) | Football and analytics terms | Writing prompts, UI copy, or docs |
| [changelog.md](changelog.md) | One line per commit | Catching up on what changed |

## Module map
Status: `planned` · `wip` · `done`

| Path | Purpose | Status | Task |
|---|---|---|---|
| `src/matchmind/config.py` | Settings from env (`Settings`, `get_settings()`) | done | 1 |
| `src/matchmind/schemas.py` | All shared pydantic models | done | 2 |
| `src/matchmind/schemas_profile.py` | Player and club profile models | wip | 3 |
| `src/matchmind/engine/pitch.py` | Pitch constants and geometry | done | 2 |
| `src/matchmind/league/` | Clubs, squads, fixtures (done); profiles, season (planned) | wip | 3, 10.4 |
| `src/matchmind/engine/` | Synthetic match engine + validator | planned | 4–10 |
| `src/matchmind/stats/` | Deterministic metrics | planned | 6, 7, 11–14 |
| `src/matchmind/store/` | SQL + tracking blob store | planned | 14 |
| `src/matchmind/pipeline/` | `matchmind build` CLI | planned | 14 |
| `src/matchmind/mcp_server/` | MCP stats tools | planned | 15 |
| `src/matchmind/agents/` | Foundry agents + orchestrator | planned | 16–20 |
| `src/matchmind/api/` | FastAPI REST + SSE | planned | 21 |
| `web/` | React frontend | planned | 22–23 |
| `infra/`, `azure.yaml` | azd + Bicep | planned | 24 |
| `scripts/check_licenses.py` | Runtime license allowlist gate | done | 1 |
| `scripts/check_wiki.py`, `.githooks/` | Wiki rule enforcement (TASK-0) | done | 1 |
| `.github/workflows/ci.yml` | CI | done | 1 |

## Governing documents
`CONSTITUTION.md` (rules) · `TASKS.md` (tracking) · `docs/superpowers/plans/2026-10-21-matchmind.md` (plan) · `docs/research/open-source-review.md` (allowed dependencies)
