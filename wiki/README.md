# MatchMind Wiki

A short, current map of the codebase. **Read this page first, then only the pages you need.** Pages describe what exists in the code *now*. Plans live in `docs/superpowers/plans/2026-10-21-matchmind.md`, and work tracking lives in `TASKS.md`.

**Last updated:** 2026-10-21 · **Latest task:** TASK-1.1 · **Code status:** scaffold only

## Current state
- Done: constitution, implementation plan, task breakdown, open-source review, this wiki.
- Built: uv project, settings (`src/matchmind/config.py`).
- Next: TASK-1.2 (CI + license gate). The user is setting up Azure for Students and Foundry (TASK-16.1).
- Blockers: none for TASK-1 to TASK-15. TASK-16.2 onward needs the Foundry deployment.

## Pages
| Page | Covers | Read when |
|---|---|---|
| [architecture.md](architecture.md) | Data flow, fast and insight lanes, components and their status | Starting any cross-cutting work |
| [data-model.md](data-model.md) | Schemas, units, ID formats, DB tables | Touching schemas, store, or API payloads |
| [engine.md](engine.md) | Synthetic match engine levels, constants, scenarios | Work in `src/matchmind/engine` or `league` |
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
| `src/matchmind/schemas.py` | All shared pydantic models | planned | 2 |
| `src/matchmind/league/` | Fictional league, squads, season | planned | 3 |
| `src/matchmind/engine/` | Synthetic match engine + validator | planned | 4–10 |
| `src/matchmind/stats/` | Deterministic metrics | planned | 6, 7, 11–14 |
| `src/matchmind/store/` | SQL + tracking blob store | planned | 14 |
| `src/matchmind/pipeline/` | `matchmind build` CLI | planned | 14 |
| `src/matchmind/mcp_server/` | MCP stats tools | planned | 15 |
| `src/matchmind/agents/` | Foundry agents + orchestrator | planned | 16–20 |
| `src/matchmind/api/` | FastAPI REST + SSE | planned | 21 |
| `web/` | React frontend | planned | 22–23 |
| `infra/`, `azure.yaml` | azd + Bicep | planned | 24 |

## Governing documents
`CONSTITUTION.md` (rules) · `TASKS.md` (tracking) · `docs/superpowers/plans/2026-10-21-matchmind.md` (plan) · `docs/research/open-source-review.md` (allowed dependencies)
