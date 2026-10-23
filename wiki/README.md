# MatchMind Wiki

A short, current map of the codebase. **Read this page first, then only the pages you need.** Pages describe what exists in the code *now*. Plans live in `docs/superpowers/plans/2026-10-21-matchmind.md`, and work tracking lives in `TASKS.md`.

**Last updated:** 2026-10-22 · **Latest task:** TASK-10.2 · **Code status:** league, profiles, level-3 engine passing all realism checks

## Current state
- Done: constitution, implementation plan, task breakdown, open-source review, this wiki.
- Built: uv project, settings (`src/matchmind/config.py`), CI, license gate (`scripts/check_licenses.py`), wiki check (`scripts/check_wiki.py` + `.githooks/pre-commit`), shared schemas and pitch geometry, 20-club Colombian barrio league with squads and fixtures, player and club profiles, chemistry, origins, transfers, legends; match file I/O (`engine/match_io.py`), level-1 engine (`engine/baseline.py`, `simulate.py`, `lineup.py`, `formations.py`), realism validator and report (`engine/validate.py`, `scripts/realism_report.py`, `docs/realism.md`), pitch control with offside filter (`stats/pitch_control.py`), xT (`stats/xt.py`, grid in `data/models/`), level-2 building blocks (`engine/kinematics.py`, `roles.py`, `modifiers.py`), ball physics (`engine/ball.py`), decisions (`engine/decisions.py`), the level-3 coupled engine (`engine/coupled.py`, `constants.py`; 16/16 realism checks).
- Next: TASK-10.3 (storylines, retrained xT, full realism report). The user is setting up Azure for Students and Foundry (TASK-16.1).
- Blockers: none for TASK-1 to TASK-15. TASK-16.2 onward needs the Foundry deployment.

## Pages
| Page | Covers | Read when |
|---|---|---|
| [architecture.md](architecture.md) | Data flow, fast and insight lanes, components and their status | Starting any cross-cutting work |
| [data-model.md](data-model.md) | Schemas, units, ID formats, DB tables | Touching schemas, store, or API payloads |
| [league.md](league.md) | Clubs, squads, latent factors, distributions, names, fixtures, profiles | Work in `src/matchmind/league` |
| [engine.md](engine.md) | Synthetic match engine levels 1–3, ball, decisions, realism | Work in `src/matchmind/engine` |
| [engine-level4.md](engine-level4.md) | Tactics, cards, subs, set pieces, scenario beats | Engine tactics, set pieces, or storylines |
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
| `src/matchmind/schemas_profile.py` | Player/club profiles, Transfer, Legend, Profiles | done | 3 |
| `src/matchmind/engine/pitch.py` | Pitch constants and geometry | done | 2 |
| `src/matchmind/league/` | Clubs, squads, fixtures, profiles, transfers, legends (done); season history (planned) | wip | 3, 10.4 |
| `src/matchmind/engine/match_io.py` | Match files (meta.json, events/frames Parquet) | done | 4.1 |
| `src/matchmind/engine/lineup.py`, `formations.py` | Line-ups, `MatchMeta`, formation anchors | done | 4.2 |
| `src/matchmind/engine/baseline.py`, `simulate.py` | Level-1 engine (fallback), shared `build_frames`; `simulate_match` dispatch | done | 4.2, 9.3 |
| `src/matchmind/engine/validate.py`, `realism_ranges.py` | Realism checks | done | 5 |
| `src/matchmind/engine/kinematics.py` | Level-2 steering, speed/accel caps, energy | done | 8.1 |
| `src/matchmind/engine/roles.py` | Role targets, defensive and offside lines, run timing | done | 8.2 |
| `src/matchmind/engine/modifiers.py` | Capped profile → behavior multipliers, match form, pair chemistry | done | 8.3 |
| `src/matchmind/engine/ball.py` | Ball flight physics, out of play, restart by last touch, deflections | done | 9.1 |
| `src/matchmind/engine/decisions.py` | On-ball options, scoring, skill-weighted choice, shot xG | done | 9.2 |
| `src/matchmind/engine/coupled.py`, `constants.py` | Level-3 event-coupled 10 Hz loop; its tunables | done | 9.3 |
| `src/matchmind/engine/tactics.py` | Phase shapes (11/10/9 players), pressing triggers, run rates | done | 10.1 |
| `src/matchmind/engine/set_pieces.py`, `scenario.py` | Corners, aerial duels, free kicks, penalties; scenario beats (TOML) | done | 10.2 |
| `scenarios/*.toml` | The 8 storylines | planned | 10.3 |
| `src/matchmind/stats/pitch_control.py` | Pitch control (vectorized Spearman) with offside filter | done | 6, 6.1 |
| `src/matchmind/stats/` (rest) | Deterministic metrics | planned | 11–14 |
| `src/matchmind/stats/xt.py`, `data/models/xt_grid.{npy,json}` | xT model and trained grid | done | 7 |
| `tests/reference/` | Vendored third-party code for parity tests (test-only) | done | 6 |
| `src/matchmind/store/` | SQL + tracking blob store | planned | 14 |
| `src/matchmind/pipeline/` | `matchmind build` CLI | planned | 14 |
| `src/matchmind/mcp_server/` | MCP stats tools | planned | 15 |
| `src/matchmind/agents/` | Foundry agents + orchestrator | planned | 16–20 |
| `src/matchmind/api/` | FastAPI REST + SSE | planned | 21 |
| `web/` | React frontend | planned | 22–23 |
| `infra/`, `azure.yaml` | azd + Bicep | planned | 24 |
| `scripts/check_licenses.py` | Runtime license allowlist gate | done | 1 |
| `scripts/check_wiki.py`, `.githooks/` | Wiki rule enforcement (TASK-0) | done | 1 |
| `scripts/realism_report.py` | Simulate N seeds and write the realism table | done | 5 |
| `scripts/train_xt.py` | Train and save the xT grid (parallel, events only) | done | 7 |
| `.github/workflows/ci.yml` | CI | done | 1 |

## Governing documents
`CONSTITUTION.md` (rules) · `TASKS.md` (tracking) · `docs/superpowers/plans/2026-10-21-matchmind.md` (plan) · `docs/research/open-source-review.md` (allowed dependencies)
