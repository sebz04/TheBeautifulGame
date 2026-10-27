# MatchMind Wiki

A short, current map of the codebase. **Read this page first, then only the pages you need.** Pages describe what exists in the code *now*. Plans live in `docs/superpowers/plans/2026-10-21-matchmind.md`, and work tracking lives in `TASKS.md`.

**Last updated:** 2026-10-22 · **Latest task:** TASK-19 · **Code status:** league, profiles, level-3 engine passing all realism checks

## Current state
- Done: constitution, implementation plan, task breakdown, open-source review, this wiki.
- Built: uv project, settings (`src/matchmind/config.py`), CI, license gate (`scripts/check_licenses.py`), wiki check (`scripts/check_wiki.py` + `.githooks/pre-commit`), shared schemas and pitch geometry, 20-club Colombian barrio league with squads and fixtures, player and club profiles, chemistry, origins, transfers, legends; match file I/O (`engine/match_io.py`), level-1 engine (`engine/baseline.py`, `simulate.py`, `lineup.py`, `formations.py`), realism validator and report (`engine/validate.py`, `scripts/realism_report.py`, `docs/realism.md`), pitch control with offside filter (`stats/pitch_control.py`), xT (`stats/xt.py`, grid in `data/models/`), level-2 building blocks (`engine/kinematics.py`, `roles.py`, `modifiers.py`), ball physics (`engine/ball.py`), decisions (`engine/decisions.py`), stats metrics and moments (`stats/`), SQL and tracking stores (`store/`), `matchmind build` (`pipeline/`, `cli.py`), the MCP stats server (`mcp_server/`), agent runtime and number checking (`agents/runtime.py`, `numbers.py`), the Tactical Analyst, Explainer, Verifier, Narrative, and Personalizer with fallback templates (`agents/`), the level-3 coupled engine (`engine/coupled.py`, `constants.py`; 16/16 realism checks), the orchestrator and live precompute of all 8 matches (`agents/orchestrator.py`, `scripts/precompute.py`, `docs/costs.md`), the API (`api/`: REST, SSE live replay, live regenerate, `/mcp`).
- Next: TASK-22 (visual direction), then TASK-23 (frontend).
- Blockers: none. Foundry `gpt-4.1-mini` is live (North Central US); Application Insights tracing is on.

## Pages
| Page | Covers | Read when |
|---|---|---|
| [architecture.md](architecture.md) | Data flow, fast and insight lanes, components and their status | Starting any cross-cutting work |
| [data-model.md](data-model.md) | Schemas, units, ID formats, DB tables | Touching schemas, store, or API payloads |
| [league.md](league.md) | Clubs, squads, latent factors, distributions, names, fixtures, profiles | Work in `src/matchmind/league` |
| [engine.md](engine.md) | Synthetic match engine levels 1–3, ball, decisions, realism | Work in `src/matchmind/engine` |
| [engine-level4.md](engine-level4.md) | Tactics, cards, subs, set pieces, scenario beats | Engine tactics, set pieces, or storylines |
| [stats.md](stats.md) | xT, pitch control, pass/speed/team metrics, moments, counterfactuals | Work in `src/matchmind/stats` |
| [agents.md](agents.md) | Agents, prompts, workflow, fallbacks | Work in `src/matchmind/agents` or `mcp_server` |
| [personalization.md](personalization.md) | Personalizer (4 personas × 5 languages, batched), fallback templates | Work on `agents/personalizer.py` or `templates.py` |
| [orchestrator.md](orchestrator.md) | Workflow graph, retries and backoff, agent-run logging, throttling, precompute | Work on `agents/orchestrator.py`, `runtime.py`, or `scripts/precompute.py` |
| [verifier.md](verifier.md) | Verifier, regeneration loop, number checking, golden set and evals | Work on `agents/verifier.py`, `numbers.py`, or `evals/` |
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
| `src/matchmind/league/` | Clubs, squads, fixtures, profiles, transfers, legends, engine-played season history (`season.py`) | done | 3, 10.4 |
| `src/matchmind/stats/player_lines.py` | Per-player match stat lines | done | 10.4 |
| `src/matchmind/stats/passes.py` | Pass quality (difficulty, xT added), accuracy | done | 11.1 |
| `src/matchmind/stats/speed.py` | Ball/shot speed, player motion, alert cues | done | 11.2 |
| `src/matchmind/stats/team.py` | PPDA, field tilt, momentum series, control vs chaos | done | 12.1 |
| `src/matchmind/stats/moments.py` | Key-moment rule triggers and merging | done | 12.2 |
| `src/matchmind/stats/baselines.py`, `deviations.py` | Season baselines, live player deviations | done | 12.3 |
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
| `scenarios/*.toml` | The 8 storylines | done | 10.3 |
| `src/matchmind/stats/pitch_control.py` | Pitch control (vectorized Spearman) with offside filter | done | 6, 6.1 |
| `src/matchmind/stats/counterfactual.py` | Counterfactual options scored like the engine | done | 13 |
| `src/matchmind/stats/xt.py`, `data/models/xt_grid.{npy,json}` | xT model and trained grid (level 3, 300 seeds) | done | 7, 10.3 |
| `tests/reference/` | Vendored third-party code for parity tests (test-only) | done | 6 |
| `src/matchmind/store/db.py` | SQL stats store (SQLite / Azure SQL), `Repo` | done | 14.1 |
| `src/matchmind/store/blob.py` | Tracking-frame store (local or Azure Blob), windowed reads | done | 14.2 |
| `src/matchmind/stats/metrics.py` | Event-exact `metrics_at`, 30 s and per-moment snapshots | done | 14.3 |
| `src/matchmind/pipeline/build_match.py`, `src/matchmind/cli.py` | `matchmind build` (scenario → stats → store) | done | 14.3 |
| `src/matchmind/mcp_server/server.py` | MCP stats server (12 read-only tools, event-exact) | done | 15 |
| `src/matchmind/agents/numbers.py` | Locale-aware number extraction and checking (Verifier rule) | done | 16.2 |
| `src/matchmind/agents/runtime.py` | Foundry chat client, FakeChatClient, agents from prompt files, run spans, MCP stats tool, tracing | done | 16.3 |
| `src/matchmind/agents/analyst.py`, `prompts/analyst.v1.md` | Tactical Analyst: which moments to explain | done | 17.1 |
| `src/matchmind/agents/explainer.py`, `prompts/explainer.v1.md` | Explainer: one insight per surfaced moment | done | 17.2 |
| `src/matchmind/agents/context.py`, `src/matchmind/clock.py` | Names and minute labels for agents; match clock | done | 17.2 |
| `scripts/record_llm_fixtures.py`, `tests/fixtures/llm/` | Live recording and replayed model fixtures | done | 17.2 |
| `src/matchmind/agents/verifier.py`, `prompts/verifier.v1.md` | Verifier (numbers, then wording), `verify_loop`, `StatsFacts` | done | 18.1 |
| `scripts/build_verifier_golden.py`, `scripts/run_foundry_eval.py`, `evals/`, `docs/evals.md` | Verifier golden set and live evaluation | done | 18.2 |
| `src/matchmind/agents/templates.py` | Fallback texts: 4 personas × 5 languages from claims | done | 19.1 |
| `src/matchmind/agents/narrative.py`, `prompts/narrative.v1.md` | Narrative: live lines and full-time recap | done | 19.2 |
| `src/matchmind/agents/personalizer.py`, `prompts/personalizer.v1.md` | Batched personalization: 4 personas, 5 languages | done | 19.3 |
| `src/matchmind/agents/orchestrator.py` | Workflow graph per window, fallbacks, resumable runs | done | 20.1 |
| `scripts/precompute.py`, `scripts/devui.py`, `docs/costs.md` | Live precompute (resumable, throttled), replay manifests, cost table; DevUI launcher | done | 20.2 |
| `src/matchmind/api/` | FastAPI REST, SSE live replay, rate-limited live regenerate, `/mcp`, CORS | done | 21 |
| `web/` | React frontend: scaffold and club theme (more in TASK-23) | wip | 22–23 |
| `infra/`, `azure.yaml` | azd + Bicep | planned | 24 |
| `scripts/check_licenses.py` | Runtime license allowlist gate | done | 1 |
| `scripts/check_wiki.py`, `.githooks/` | Wiki rule enforcement (TASK-0) | done | 1 |
| `scripts/realism_report.py` | Simulate N seeds and write the realism table | done | 5 |
| `scripts/train_xt.py` | Train and save the xT grid (parallel, events only) | done | 7 |
| `.github/workflows/ci.yml`, `nightly.yml` | CI; nightly `slow` tests | done | 1, 10.4 |

## Governing documents
`CONSTITUTION.md` (rules) · `TASKS.md` (tracking) · `docs/superpowers/plans/2026-10-21-matchmind.md` (plan) · `docs/research/open-source-review.md` (allowed dependencies)
