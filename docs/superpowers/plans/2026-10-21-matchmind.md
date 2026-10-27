# MatchMind Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build MatchMind, a multi-agent Microsoft Foundry system that generates synthetic football matches, computes match intelligence deterministically, and turns it into verified, personalized, multi-language insights rendered beside an animated 2D match.

**Architecture:** A seeded, event-coupled match engine writes events (Azure SQL) and 10 Hz tracking (Blob/Parquet). A deterministic stats engine computes xT, pitch control, pass quality, speeds, team metrics, key moments, and counterfactuals, and exposes them through an MCP server. Agent Framework agents on Foundry (Analyst → Explainer → Verifier → Narrative → Personalization, plus phase-two agents) read numbers only through MCP and write verified insights back to shared state. A FastAPI service streams replays and insights over SSE to a React frontend.

**Tech Stack:** Python 3.12, uv, NumPy, pandas, pyarrow, SQLAlchemy 2, pydantic 2, FastAPI, sse-starlette, `mcp` (FastMCP), Microsoft Agent Framework (`agent-framework-core`, `agent-framework-foundry` → `FoundryChatClient`, `agent-framework-orchestrations`; `agent-framework-devui` as a dev-only extra), azure-identity, azure-monitor-opentelemetry; React 18, Vite, TypeScript, Tailwind, Zustand, visx, Vitest, Playwright, axe-core; Azure Developer CLI (`azd`) + Bicep; GitHub Actions.

**Spec:** `BeautifulGame_Data_Pipeline.md` + `CONSTITUTION.md` + `Microsoft_Premier_League_Hackathon_Rules.pdf` (§4.1 challenge, §4.4 submission, §6 judging). Open-source choices: `docs/research/open-source-review.md`. Codebase map: `wiki/README.md`.

## Global Constraints

- Every number shown to users comes from `src/matchmind/stats` or the store; agents fetch through MCP only (Constitution I).
- No text is visible until the Verifier passes it; failures fall back to deterministic templates (Constitution II).
- Only fictional clubs and players; no real data in training; no third-party trademarks (Constitution III).
- Same `seed` + scenario → byte-identical `events.parquet` (Constitution IV).
- Tests never call a live model; use `FakeChatClient` (Constitution IV).
- Pitch 105 × 68 m, origin bottom-left; tracking 10 Hz; `t` = seconds since kickoff of the current period, `period ∈ {1, 2}`.
- Personas: `analyst`, `casual`, `club_fan`, `player_focus`. Languages: `en`, `es`, `pt`, `fr`, `ar` (Arabic RTL).
- Fast-lane overlays ≤ 1 s after their event; insight lane ≤ 10 s after their moment in live replay.
- Commit messages start with the task or sub-task ID: `TASK-N: <summary>` or `TASK-N.M: <summary>` (sub-tasks are listed in `TASKS.md`).
- Every commit that changes code updates the affected `wiki/` pages and adds one line to `wiki/changelog.md` (TASK-0).
- Third-party code and packages come only from the Adopt list in `docs/research/open-source-review.md`. Each one is credited in `THIRD_PARTY_NOTICES.md`. No real-world match, event, or tracking data is used anywhere.
- Open-ended tuning steps are timeboxed (stated in the step). When a timebox runs out, record the remaining deviations in `docs/realism.md` and move on.
- Secrets only in `.env` (git-ignored) or managed identity; `.env.example` lists the keys with no values.
- Model access goes only through a Foundry deployment, set by env vars `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL_DEPLOYMENT` (default `gpt-4.1-mini`).

## Review Focus

1. **Localized numbers in the Verifier:** "1,5", "12.000", "doce", and Arabic-Indic "١٢" must be parsed and matched to the stats, or rejected; they must never be silently ignored. Pinned in Task 16.
2. **Uneven player counts (red card, 10 v 11):** pitch control, PPDA, formation shape, and tactics must work with 10 players without NaN or a crash. Pinned in Tasks 6, 10, 12.
3. **Model failure (timeout, HTTP 429, malformed JSON):** the pipeline retries with backoff, then falls back to a template; the UI never shows an empty card. Pinned in Task 20.
4. **Edge positions:** passes ending on the touchline or goal line, `x = 105.0`, and the ball out of play must give finite xT, pitch control, and pass difficulty. Pinned in Tasks 6, 7, 11.
5. **Seek and reconnect during live replay:** jumping in the timeline or reconnecting SSE with `from_t` must produce no duplicate and no missing overlays. Pinned in Task 21.

---

## File Structure

```
pyproject.toml  uv.lock  .env.example  .gitignore  docker-compose.yml  Dockerfile
src/matchmind/
  config.py                 # Settings (pydantic-settings) from env
  schemas.py                # All shared pydantic models (single source of truth)
  league/league.py          # Fictional 20-club Colombian barrio league, squads
  league/season.py          # Fictional season history + milestones
  engine/pitch.py           # Coordinates, zones, geometry helpers
  engine/baseline.py        # Level 1: formation-anchored sim (kept as fallback)
  engine/kinematics.py      # Player motion with speed/accel caps, fatigue
  engine/ball.py            # Ball flight physics
  engine/tactics.py         # Formations, phases, pressing triggers
  engine/decisions.py       # On-ball option scoring (pitch control × xT + skill noise)
  engine/scenario.py        # Storyline script schema + hooks (red card, sub, goal timing)
  engine/simulate.py        # simulate_match(): the coupled engine loop
  engine/validate.py        # Realism checks vs Premier League ranges
  stats/pitch_control.py    # Spearman-style pitch control (after Friends of Tracking)
  stats/xt.py               # xT trained on synthetic events
  stats/passes.py           # Pass distance, accuracy, difficulty
  stats/speed.py            # Ball/shot speed, player distance, sprint alerts
  stats/team.py             # PPDA, field tilt, momentum, control-vs-chaos
  stats/moments.py          # Rule triggers → Moment candidates
  stats/counterfactual.py   # Best alternative pass
  store/db.py               # SQLAlchemy models + repository (SQLite local, Azure SQL cloud)
  store/blob.py             # Tracking Parquet I/O (local fs or Azure Blob)
  pipeline/build_match.py   # CLI: generate → compute → store one match
  mcp_server/server.py      # FastMCP stats tools
  agents/runtime.py         # Foundry client factory, FakeChatClient, tracing
  agents/numbers.py         # Locale-aware number extraction + claim checking
  agents/prompts/*.md       # One prompt file per agent, versioned
  agents/analyst.py  explainer.py  verifier.py  narrative.py  personalizer.py
  agents/scenario_designer.py  ingest.py  overlay_director.py   # phase two
  agents/templates.py       # Deterministic fallback text per language
  agents/orchestrator.py    # Agent Framework workflow + retries + precompute
  api/app.py                # FastAPI app, mounts MCP at /mcp
  api/routes_*.py           # matches, insights, live (SSE), regenerate
  api/ratelimit.py
web/                        # React + Vite + TS + Tailwind
infra/main.bicep  infra/modules/*.bicep
.github/workflows/ci.yml  deploy.yml
tests/  (mirrors src/matchmind/)  tests/fixtures/
data/matches/<match_id>/   # git-ignored generated output
```

---

## Order and sub-tasks

`TASKS.md` splits every task larger than about half a day into sub-tasks `TASK-N.M`. Each sub-task carries its own tests and commit. The steps below are grouped by parent task, and each sub-task covers the matching subset of those steps (named in its `TASKS.md` line).

Critical path: 1 → 2 → 4 → 6/7 → 8 → 9 → 10 → 11/12/13 → 14 → 15 → 16 → 17 → 18 → 19 → 20 → 21 → 23 → 24 → 31.
Can run alongside the critical path: 3 (after 2), 5 (after 4), 22 (any time after 1; do it early so the user's design choice never blocks Task 23), 16.1 (user Azure setup: start immediately).
Suggested days: Day plan is kept outside the repo. Profiles and baselines (TASK-3.2, 8.3, 10.4, 10.5, 12.3) add about 1.75 days, absorbed by the Day 6 buffer and a trimmed Phase 2 (TASK-34, then TASK-26).

### Task 0: Maintain the wiki (standing)

**Files:** `wiki/*.md`, `CLAUDE.md`.

Rule: every commit that changes code also updates (1) the wiki page for each area it touched, keeping that page under 150 lines and describing what exists now, not plans, (2) the module map in `wiki/README.md` if files were added, moved, or removed, and (3) one line in `wiki/changelog.md` (`YYYY-MM-DD · TASK-N.M · <commit summary> · <pages touched>`). Decisions that change the plan go in `wiki/decisions.md`. A future session reads `wiki/README.md` first, then only the pages it needs.

- [ ] **Check (each commit):** `scripts/check_wiki.py` (added in TASK-1.3) fails if a commit changes `src/` or `web/src/` without touching `wiki/`, or if any wiki page is over 150 lines. It runs in CI and as a pre-commit hook.

## Phase 1: Core pipeline (Tasks 1–25)

### Task 1: Repo scaffold, tooling, CI

**Files:** Create `pyproject.toml`, `.gitignore`, `.env.example`, `src/matchmind/__init__.py`, `src/matchmind/config.py`, `tests/test_config.py`, `.github/workflows/ci.yml`; modify `README.md`.

**Interfaces:** Produces `matchmind.config.Settings` with fields `db_url: str = "sqlite:///data/matchmind.db"`, `data_dir: Path = Path("data")`, `foundry_project_endpoint: str | None`, `foundry_model_deployment: str = "gpt-4.1-mini"`, `appinsights_connection_string: str | None`, `blob_account_url: str | None`, and `get_settings() -> Settings` (cached).

- [ ] **Step 1: Write the failing test.** `test_settings_defaults`: with a clean env, `get_settings().db_url == "sqlite:///data/matchmind.db"` and `foundry_model_deployment == "gpt-4.1-mini"`. `test_settings_env_override`: `monkeypatch.setenv("MATCHMIND_DB_URL", "sqlite://")` makes `db_url == "sqlite://"`.
- [ ] **Step 2: Run** `uv run pytest tests/test_config.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `Settings(BaseSettings, env_prefix="MATCHMIND_")`. Exception: Foundry vars read unprefixed (`FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT`) via `validation_alias`. `.gitignore` covers `.env`, `data/`, `.venv/`, `node_modules/`, `web/dist/`. Dev deps: pytest, pytest-asyncio, ruff, mypy, hypothesis.
- [ ] **Step 4: Run** `uv run pytest && uv run ruff check . && uv run mypy src`. Expected: all pass.
- [ ] **Step 5: CI.** `ci.yml` runs on push and PR: `uv sync`, ruff, mypy, pytest. A web job (no-op until Task 23).
- [ ] **Step 6: License gate.** Create `THIRD_PARTY_NOTICES.md` and `scripts/check_licenses.py`, which runs `pip-licenses --format=json` and fails on any runtime dependency whose license is not MIT, BSD (incl. 0BSD), Apache-2.0, ISC, PSF, MPL-2.0, Zlib, or CC0. CI runs it.
- [ ] **Step 7: Commit** `TASK-1.x: …` (one commit per sub-task in `TASKS.md`).

### Task 2: Shared schemas and pitch geometry

**Files:** Create `src/matchmind/schemas.py`, `src/matchmind/engine/pitch.py`, `tests/test_schemas.py`, `tests/engine/test_pitch.py`.

**Interfaces (Produces, used everywhere):**
- `EventType = Literal["kickoff","pass","carry","shot","tackle","interception","pressure","foul","card","sub","goal","out","save","clearance"]`
- `Event(event_id: str, match_id: str, period: int, t: float, type: EventType, team_id: str, player_id: str | None, x: float, y: float, end_x: float | None, end_y: float | None, outcome: bool | None, receiver_id: str | None, ball_speed_ms: float | None, extras: dict[str, Any] = {})`. `event_id` format: `f"{match_id}-e{n:05d}"`.
- `PlayerPos(player_id: str, team_id: str, x: float, y: float, vx: float, vy: float)`
- `TrackingFrame(match_id: str, frame: int, period: int, t: float, ball: tuple[float, float, float], players: list[PlayerPos])`
- `Player(player_id, name, club_id, number: int, position: Literal["GK","DF","MF","FW"], pace: float, skill: float, stamina: float)` (attributes in 0–1)
- `Club(club_id, name, short, primary_color: str, secondary_color: str, formation: str)`
- `MatchMeta(match_id, seed: int, home: Club, away: Club, home_squad: list[Player], away_squad: list[Player], scenario_id: str, engine_version: str, stadium: str, kickoff_iso: str, added_time_s: tuple[float, float])`
- `MatchData(meta: MatchMeta, events: list[Event], frames: list[TrackingFrame])`
- `Moment(moment_id, match_id, period, t_start, t_end, kind: Literal["momentum_swing","pressing_collapse","formation_shift","big_chance","goal","red_card","sprint_alert"], level: Literal["game","team","player"], team_id: str | None, player_id: str | None, trigger_metric: str, trigger_value: float, event_ids: list[str])`
- `Claim(text: str, metric: str, value: float, unit: str, ref: str)` (`ref` = event_id or `"metric:<name>@<t>"`)
- `Insight(insight_id, moment_id, match_id, level, headline: str, why: str, recommendation: str, claims: list[Claim], event_ids: list[str], confidence: Literal["high","medium","low"], verified: bool, source: Literal["agent","template"], trace_id: str | None, prompt_version: str)`
- `PersonalizedText(insight_id, persona: Persona, lang: Lang, headline: str, body: str, verified: bool, club_id: str | None = None, player_id: str | None = None)` with `Persona` / `Lang` literals from the Global Constraints. `club_id` is set for `club_fan` texts, `player_id` for `player_focus` texts.
- `Variant(persona: Persona, club_id: str | None = None, player_id: str | None = None)`
- `OverlayCue(cue_id, match_id, period, t_in: float, t_out: float, kind: Literal["name_tag","speed_alert","distance_alert","stat_card","freeze_frame","insight","narrative"], priority: int, payload: dict[str, Any])`
- `pitch.py`: `PITCH_LENGTH = 105.0`, `PITCH_WIDTH = 68.0`, `clamp_to_pitch(x, y) -> tuple[float, float]`, `zone_index(x, y, nx=16, ny=12) -> tuple[int, int]` (edges map inside the grid), `distance(a, b) -> float`.

- [ ] **Step 1: Failing tests.** `test_event_roundtrip_json` (model → JSON → model equal); `test_event_id_format` (regex `^.+-e\d{5}$` enforced by validator); `test_zone_index_edges`: `zone_index(105.0, 68.0) == (15, 11)`, `zone_index(0, 0) == (0, 0)`, `zone_index(-1, 70) == (0, 11)`.
- [ ] **Step 2: Run** `uv run pytest tests/test_schemas.py tests/engine/test_pitch.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the models (pydantic v2, `frozen=True` for Event and PlayerPos) and the geometry.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `TASK-2: shared schemas and pitch geometry`.

### Task 3: Fictional Colombian league and player/club profiles

**Files:** Create `src/matchmind/league/clubs.py` (the 20 approved clubs), `league/league.py`, `league/fixtures.py`, `league/profiles.py`, `league/names.py`, `src/matchmind/schemas_profile.py`, `tests/league/test_league.py`, `tests/league/test_profiles.py`, `tests/fixtures/real_club_blocklist.txt`, `tests/fixtures/real_player_blocklist.txt`.

**Approved clubs (fixed, not generated; re-themed from LA in TASK-3.5):** Bogotá: Atlético Chapinero, Club Deportivo Usaquén, Sporting La Candelaria, Unión Teusaquillo, Deportivo Suba. Medellín: Atlético Laureles, Sporting El Poblado, Deportivo Belén, Unión Manrique. Cali: San Antonio Fútbol Club, Deportivo San Fernando, Atlético Siloé. Barranquilla: Atlético El Prado, Unión Barrio Abajo, Deportivo Rebolo. Cartagena: Sporting Getsemaní, Manga Fútbol Club. Bucaramanga: Atlético Cabecera. Santa Marta: Club El Rodadero. Manizales: Deportivo Chipre. Derbies: Chapinero–Usaquén, Laureles–El Poblado, San Antonio–San Fernando, El Prado–Barrio Abajo, Getsemaní–Manga. Nationalities: about 68% Colombian, the rest South American. Money in USD millions (`*_m`) at Colombian-league scale (player value median about $0.5m, stars $5–15m).

**Interfaces:**
- TASK-3.1: `CLUBS` (20 entries with id, name, 3-letter short code, stadium, capacity, founded year), `build_league(seed=2026) -> League(clubs, squads: dict[str, list[Player]])` (20 × 20 players: 2 GK, 7 DF, 7 MF, 4 FW), `derbies() -> list[tuple[str, str]]`, `build_fixtures(league, seed, start_date="2026-08-15") -> list[Fixture(round, date, home_id, away_id)]` (38-round double round robin, 10 matches per round, every club once per round, home/away balanced).
- TASK-3.2: `schemas_profile.py` (kept separate from `schemas.py`; `Player.pace/skill/stamina` become summary ratings derived from the profile; `skill` = decision quality):
  - `PlayerProfile(player_id, personality: Personality(composure, aggression, confidence, leadership, consistency), style: Style(position, secondary_position, role, work_rate, tactical_discipline, risk_tolerance), technical: Technical(passing, first_touch, dribbling, finishing, crossing, tackling, aerial, shot_stopping, distribution), origin: Origin(kind: academy|signed|loan, joined_year, signed_from, fee_m), career: Career(nationality, birth_year, years_pro, stage: rookie|prime|veteran, club_apps, club_goals, caps, contract_until, market_value_m, contract_negotiations, transfer_interest: list[str], retirement_risk), discipline: Discipline(career_yellows, career_reds, season_yellows, suspended_until_round), status: Status(injury: fit|returning|doubtful, games_missed, captain, preferred_foot, height_cm), flags: is_academy, is_new_signing, is_former_rival, is_returning_from_injury)`. Ratings are in [0, 1]. Career ambitions are narrative-only (no engine effect).
  - `ClubProfile(club_id, tactical_identity: TacticalIdentity(press_intensity, line_height, tempo, width, directness, build_up: short|mixed|direct), management: Management(manager_name, manager_style: possession|pressing|counter|pragmatic, manager_tenure_years, job_security), culture: academy_first|win_now|underdog|fan_owned, ownership: long_standing|new_owner|fan_owned, owner_since, transfer_budget_m, wage_bill_m, last_finish, status: promoted|title_contender|mid_table|relegation_fight, home_advantage)` plus `chemistry(club_id) -> dict[tuple[str, str], float]` (pairwise, from years together, academy, shared language, manager tenure).
  - `Transfer(player_id, from_club, to_club, year, fee_m, kind: permanent|loan|free)`, `Legend(name, club_id, era, apps, goals)`.
  - `build_profiles(league, seed) -> Profiles(players, clubs, transfers, legends)`. Generation uses a latent-factor model: each player draws hidden quality, temperament and athleticism factors; attributes = position prior + factor loadings + noise, so correlations are realistic (aggression ↔ cards, age ↔ leadership, quality ↔ fee and market value, club budget ↔ squad quality).

- [ ] **TASK-3.1 tests:** `test_league_deterministic`; `test_league_shape` (20 clubs, 20 players each, unique ids and short codes, unique shirt numbers per club); `test_fixtures_round_robin` (38 rounds × 10 matches, each pair meets twice with home and away swapped); `test_no_real_names` (no club name, nickname, or player name matches the blocklists: the 20 Premier League clubs, 10 famous European clubs, Colombian Primera A/B and historical clubs, and Colombian club nicknames such as Verdolagas, Embajadores, Cardenales, Diablos Rojos, Tiburones, Pijaos).
- [ ] **Distribution rules (TASK-3.2/3.3):** ratings are `sigmoid(0.7 · z)` of a standardized latent combination, so they are bell-shaped around 0.5; money (fees, market values, budgets, wages) is log-normal (right-skewed); ages are a truncated normal (mean ≈ 26.5, SD ≈ 4.2, range 17–37). Tests: `test_rating_distributions`, `test_money_right_skewed`, `test_demographics`.
- [ ] **TASK-3.2–3.4 tests** (split across the three sub-tasks): `test_profiles_deterministic`; `test_ratings_bounded`; `test_correlations` (over 400 players: corr(aggression, career_yellows) > 0.3, corr(quality factor, fee_m among signed players) > 0.4, veterans' mean leadership > rookies'); `test_transfers_consistent` (every `signed_from` in-league club has a matching `Transfer`; `is_former_rival` true iff a past club is the derby rival); `test_career_stage_rule` (rookie ≤ 2 years pro, veteran ≥ 10).
- [ ] **Commits:** `TASK-3.1` (league, fixtures), `TASK-3.2` (player profiles), `TASK-3.3` (club profiles, chemistry), `TASK-3.4` (origins, transfers, legends), `TASK-3.5` (Colombian re-theme: clubs, derbies, nationalities, names, money scale, compatriot chemistry, blocklists). Season results, standings, and milestones come from TASK-10.4 (engine-simulated), not from this task.

### Task 4: Engine level 1, formation-anchored baseline (unblocks everything downstream)

**Files:** Create `src/matchmind/engine/baseline.py`, `src/matchmind/engine/simulate.py` (entry point that dispatches by `level`), `tests/engine/test_baseline.py`.

**Interfaces:** Consumes Task 2 and 3 models. Produces `simulate_match(meta: MatchMeta, scenario: Scenario | None = None, level: Literal[1, 3] = 3) -> MatchData`. Until Task 9 lands, `level=3` raises `NotImplementedError` and tests use `level=1`. Produces `write_match(data: MatchData, out_dir: Path) -> None` / `read_match(out_dir: Path) -> MatchData` (events and frames as Parquet, meta as JSON).

- [ ] **Step 1: Failing tests.**
  - `test_deterministic`: two runs with seed 7 give identical events.
  - `test_frame_rate`: `len(frames) == sum(round((2700 + a) * 10) for a in meta.added_time_s)`, and consecutive frames within a period are 0.1 s apart.
  - `test_pass_endpoints_consistent`: for every completed pass, the receiver's tracked position at `t + flight_time` is within 2.0 m of `(end_x, end_y)`, and the passer is within 1.5 m of `(x, y)` at `t`.
  - `test_eleven_per_side_without_cards`.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement.** Each player's target = formation anchor + block shift toward the ball (`0.35 × (ball − centre)`), compressed in width (`0.75`) out of possession, with exponential smoothing. Events come from a Markov possession chain (pass / carry / shot / turnover probabilities by zone). The receiver is moved toward the pass end point so endpoints are consistent.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `TASK-4: level-1 baseline engine and match I/O`.

### Task 5: Realism validator

**Files:** Create `src/matchmind/engine/validate.py`, `src/matchmind/engine/realism_ranges.py`, `tests/engine/test_validate.py`, `scripts/realism_report.py`.

**Interfaces:** Produces `RANGES: dict[str, tuple[float, float]]`, `validate_match(data: MatchData) -> RealismReport`, and `validate_many(datas) -> RealismReport`. `RealismReport(checks: list[Check(name, value, lo, hi, ok)], ok: bool)`.

Ranges (per team per match unless stated): `passes` 350–650; `pass_completion` 0.74–0.90; `shots` 5–22; `shots_on_target_ratio` 0.25–0.50; `possession` 0.30–0.70; `ppda` 6–20; `tackles` 10–25; `distance_km_outfield_player` 9.0–13.0; `top_speed_ms` 7.5–10.0; `sprints_per_outfield_player` (> 7.0 m/s for ≥ 1 s) 10–50. Over 20 seeds: mean `goals_per_match` 2.2–3.4.

- [ ] **Step 1: Failing tests.** `test_flags_out_of_range` (a synthetic MatchData with 900 passes → `passes` check fails); `test_report_json_serializable`.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** validation (distance and speed computed from frames).
- [ ] **Step 4: Run** the tests. Expected: PASS. Then run `uv run python scripts/realism_report.py --level 1 --seeds 20` and record the baseline report in `docs/realism.md` (failures are expected at level 1).
- [ ] **Step 5: Commit** `TASK-5: realism validator and baseline report`.

### Task 6: Pitch control

**Files:** Create `src/matchmind/stats/pitch_control.py`, `tests/stats/test_pitch_control.py`.

**Interfaces:** Produces `PCParams` (defaults from Spearman 2018 / Friends of Tracking: `max_player_speed=5.0`, `reaction_time=0.7`, `tti_sigma=0.45`, `lambda_att=4.3`, `kappa_def=1.0`, `average_ball_speed=15.0`). Produces `pitch_control_at(frame: TrackingFrame, attacking_team: str, targets: np.ndarray[N, 2], params=PCParams()) -> np.ndarray[N]` (probability in [0, 1]) and `pitch_control_grid(frame, attacking_team, nx=32, ny=21) -> np.ndarray[ny, nx]`.

- [ ] **Step 1: Failing tests.**
  - `test_symmetry`: a mirrored frame gives a grid equal to `1 − grid` mirrored, within 1e-6.
  - `test_attacker_alone`: a target next to a lone attacker → > 0.95.
  - `test_ten_vs_eleven`: a frame with 10 home players → all values finite and in [0, 1].
  - `test_edge_targets`: targets at `(105, 68)` and `(0, 34)` → finite.
  - `test_parity_with_reference`: on 5 fixture frames, the result matches the Friends of Tracking reference implementation within 0.02 per cell. The reference is the relevant functions from `LaurieOnTracking/Metrica_PitchControl.py` (MIT), vendored into `tests/reference/` with the license header kept; test-only, never imported by `src/`.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** a vectorized NumPy version of the Spearman integration (time-to-intercept with a logistic sigma). Credit the Friends of Tracking code (MIT) in the module docstring and README.
- [ ] **Step 4: Run** the tests. Expected: PASS. Benchmark: a 32×21 grid in < 50 ms (`pytest -k bench`).
- [ ] **Step 5: Commit** `TASK-6: pitch control`.

### Task 6.1: Offside filter for pitch control

**Why:** without offside, pitch control credits attackers standing behind the defensive line. Counterfactuals (Task 13) would then recommend illegal passes, and level-3 decisions (Task 9) would reward loitering offside.

**Files:** Modify `src/matchmind/engine/pitch.py`, `src/matchmind/stats/pitch_control.py`, `src/matchmind/engine/validate.py` (reuse the shared direction helper); test `tests/stats/test_offside.py`, `tests/engine/test_pitch.py`.

**Interfaces:**
- `engine/pitch.py`: `attacks_right(is_home: bool, period: int) -> bool` (home attacks right in period 1).
- `stats/pitch_control.py`: `offside_players(frame, attacking_team, attacks_right: bool, tol=0.2) -> set[str]`. An attacker is offside when they are beyond `max(second-last defender, ball, halfway line) + tol` in the attacking direction. This is the reference's `check_offsides` rule, with the direction passed in instead of inferred from the keeper. Simple rule only: no "interfering with play" and no VAR margins.
- `pitch_control_at(..., attacks_right: bool | None = None)` and `pitch_control_grid(...)` take the same argument. When `attacks_right` is given, offside attackers are dropped before integration; `None` keeps the old behavior (no direction known).

- [ ] **Tests:** `test_attacks_right_by_period`; `test_offside_rule_cases` (beyond the second-last defender → offside; level within `tol` → onside; in own half → onside; behind the ball → onside; works in both directions); `test_offside_matches_reference` (same set as the vendored `check_offsides` on the 5 parity frames); `test_offside_striker_gets_no_control` (a lone striker behind the line: control near them falls from > 0.5 to < 0.5 with the filter); `test_parity_with_reference_offsides` (grid within 0.02 of the reference run with `offsides=True`).
- [ ] **Commit** `TASK-6.1: offside filter for pitch control`.

### Task 7: xT trained on synthetic events

**Files:** Create `src/matchmind/stats/xt.py`, `tests/stats/test_xt.py`, `scripts/train_xt.py`, `data/models/xt_grid.npy` (generated and committed as a small artifact, 16×12 floats).

**Interfaces:** Produces `train_xt(events: Iterable[Event], nx=16, ny=12, iters=50) -> np.ndarray[ny, nx]` (value iteration after Singh 2019), `load_xt() -> np.ndarray`, `xt_value(grid, x, y) -> float`, and `xt_added(grid, event: Event) -> float | None` (end minus start for completed passes and carries, else None).

- [ ] **Step 1: Failing tests.**
  - `test_monotone_toward_goal`: the mean of the last column > the mean of the first column.
  - `test_values_bounded`: all values in [0, 1].
  - `test_edge_lookup`: `xt_value(grid, 105.0, 68.0)` is finite.
  - `test_xt_added_none_for_failed_pass`.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the move/shoot probabilities, the transition matrix, and value iteration in NumPy. Use socceraction (MIT) only as a cross-check in the tests, not at runtime.
- [ ] **Step 4: Run** the tests. Expected: PASS. Run `uv run python scripts/train_xt.py --seeds 200 --level 1`, then commit the grid. This grid is retrained in Task 10.
- [ ] **Step 5: Commit** `TASK-7: xT trained on synthetic data`.

### Task 8: Engine level 2, kinematic agent-based players

**Files:** Create `src/matchmind/engine/kinematics.py`, `tests/engine/test_kinematics.py`.

**Interfaces:** Produces `PlayerState(pos: np.ndarray, vel: np.ndarray, energy: float)`, `step_player(state, target: np.ndarray, urgency: float, attrs: Player, dt=0.1) -> PlayerState`, and the constants `V_MAX = 9.5 + 0.8 * pace` (m/s), `A_MAX = 3.5` (m/s²), `DECEL_MAX = 5.0`. Energy drains with speed², `energy ∈ [0, 1]`, and effective `V_MAX` scales by `0.85 + 0.15 * energy`.

Roles produce targets: `role_target(role, ctx) -> (target, urgency)` for `mark`, `press`, `cover`, `support`, `run_in_behind`, `hold_line`, and `gk_position`. `run_in_behind` aims to arrive level with the last defender as the pass is played. The release moment is the player's **timing**: early release by `timing_error_s` (drawn per run from a normal distribution with SD `RUN_TIMING_SD_S = 0.35`, scaled by the timing modifier from Task 8.3) leaves the runner offside. `hold_line` steps up together to play offside.

- [ ] **Step 1: Failing tests.**
  - `test_speed_cap`: after 10 s chasing a far target, speed ≤ `V_MAX`.
  - `test_accel_cap`: |Δv| per step ≤ `A_MAX * dt + 1e-9`.
  - `test_fatigue_reduces_top_speed`: energy 0.2 gives a lower top speed than energy 1.0.
  - `test_hold_line_offside`: defenders' `hold_line` targets share an x within 1.5 m.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** steering (seek with arrival) clipped by the caps, plus the role targets.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `TASK-8: level-2 kinematic players and roles`.

### Task 8.3: Modifier layer (profiles → behavior)

**Files:** Create `src/matchmind/engine/modifiers.py`, `tests/engine/test_modifiers.py`.

**Interfaces:** `Modifiers.for_player(profile, club_profile, ctx) -> PlayerMods` and `Modifiers.for_team(club_profile, ctx) -> TeamMods`. `ctx` = minute, score difference, home/away, energy, confidence state, active scenario beats. Each effect is a multiplier `1 + clip(effect, ±cap)`, with `SUBTLE_CAP = 0.06` by default and `STORYLINE_CAP = 0.20` only while a scenario beat targets that player or team. The mapping is the table in `wiki/engine.md`. Composure scales decision temperature under pressure; aggression raises tackle, foul, and press urgency; confidence is a match state that rises after successes and falls after errors; leadership steadies teammates; consistency sets match-day form variance; work rate drives off-ball distance and energy drain; tactical discipline sets how tightly a player holds their formation anchor; risk tolerance weights xT gain against completion probability; each technical rating drives the error of its own action; injury lowers starting energy; schedule congestion lowers starting energy; home advantage adds composure and confidence; chemistry raises completion between a pair and makes the receiver start runs earlier; **run timing** (the spread of `timing_error_s`) tightens with tactical discipline, composure, and experience and loosens with fatigue (subtle cap, like every player trait). Every applied modifier above 0.01 is written to `Event.extras["mods"]` so the Explainer can cite causes.

- [ ] **Tests:** `test_caps` (no effect exceeds `SUBTLE_CAP` without a beat, or `STORYLINE_CAP` with one); `test_directions` (a +aggression profile gives a higher foul multiplier, and so on for every mapped attribute); `test_mods_recorded_in_extras`.
- [ ] **Commit** `TASK-8.3: modifier layer`.

### Task 9: Engine level 3, event-coupled loop with ball physics and decisions

**Files:** Create `src/matchmind/engine/ball.py`, `src/matchmind/engine/decisions.py`; modify `src/matchmind/engine/simulate.py`; test `tests/engine/test_ball.py`, `tests/engine/test_decisions.py`, `tests/engine/test_simulate.py`.

**Interfaces:**
- `ball.py`: `flight(start, end, kind: Literal["ground","lofted","shot"], speed_ms) -> Trajectory` (`positions_at(t)`, `duration`), with drag `k = 0.05`, ground rolling friction `0.25`. Pass speeds are drawn from 10–22 m/s (ground) and shot speeds from 18–32 m/s.
- `decisions.py`: `Option(kind, target_player_id | None, end: tuple, score: float)`; `enumerate_options(frame, carrier_id, ctx) -> list[Option]`; `score_option(opt, pc_prob, xt_gain, risk) -> float` = `pc_prob * xt_gain − risk_penalty`; `choose(options, skill: float, rng) -> Option`. Choice is softmax with temperature `0.05 + 0.6 * (1 − skill)`, so lower-skill players choose worse options more often. Options are scored with offside-filtered pitch control (Task 6.1), so passes to players who are visibly offside score near zero. A pass to a runner who *becomes* offside through a mistimed run is still possible; it ends in an `offside` event (new `EventType`, with `extras.timing_error_s` and active mods) and an indirect free kick to the defending team. The chosen option and the best-scored alternative are both written into `Event.extras` (`chosen_score`, `best_score`, `best_option`).
- **Out of play follows the ball** (`ball.py`): any trajectory that crosses a touchline or goal line ends play at the crossing point, and the **last touch** decides the restart (throw-in, goal kick, or corner; `restart_after_out` in `baseline.py` already has the rule). New ways out: `clearance` (a defender under pressure in his own third boots it long or out; new `EventType`), **blocked shots** (a defender on the shot line deflects it, sometimes behind for a corner; `shot` with `extras.blocked`), and **parried saves** (a `save` with `extras.parried` sends the ball loose or behind). Real levels are about 40–45 throw-ins, 15–18 goal kicks, and about 10 corners per match.
- `simulate.py` level 3: a single 10 Hz loop. Tactics (Task 10 stub: fixed phase shape) → role targets → `step_player` → if the carrier has the ball and a decision tick (every 0.8–2.0 s) arrives, `choose` → ball flight → an interception check using pitch control at the arrival point (a Bernoulli draw) → events emitted from simulation state.

- [ ] **Step 1: Failing tests.**
  - `test_flight_duration`: a 30 m ground pass at 15 m/s takes 2.0–2.6 s.
  - `test_choice_skill`: across 1,000 draws, skill 0.95 picks the best option > 70% of the time and skill 0.2 picks it < 45%.
  - `test_level3_consistency`: events and frames agree (Task 4's endpoint test applied at level 3).
  - `test_level3_deterministic`.
  - `test_offside_called_on_mistimed_run`: a fixture where the runner releases 0.5 s early → the pass produces an `offside` event, then a free kick to the defenders.
  - `test_validator_counts_offsides`: `RANGES["offsides"] = (0, 6)` per team per match is checked by `validate_match`.
  - `test_out_of_play_by_last_touch`: fixtures where the ball crosses the goal line off a defender → corner; off an attacker → goal kick; over a touchline → throw-in to the other team.
  - `test_corners_happen`: over 20 seeds, mean corners per team is above 2 (level 1 produces 0).
  - `test_set_piece_ranges`: the validator checks `throw_ins` 15–30, `goal_kicks` 4–12, `corners` 2–9, and `fouls` 8–18 per team.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the module functions and the loop.
- [ ] **Step 4: Run** the tests plus `scripts/realism_report.py --level 3 --seeds 20`, and tune constants until every check passes except `goals_per_match` (tuned in Task 10). **Timebox: 3 hours of tuning.** Put all tunable constants in `engine/constants.py` so tuning never touches logic.
- [ ] **Step 5: Commit** `TASK-9: level-3 event-coupled engine`.

### Task 10: Engine level 4, tactics, phases, fatigue, scenarios

**Files:** Create `src/matchmind/engine/tactics.py`, `src/matchmind/engine/scenario.py`, `scenarios/*.yaml` (8 storylines); modify `simulate.py`; test `tests/engine/test_tactics.py`, `tests/engine/test_scenario.py`.

**Interfaces:**
- `Phase = Literal["build_up","mid_block","low_block","counter","high_press","set_piece"]`; `formation_shape(formation: str, phase: Phase, n_players: int) -> np.ndarray[n, 2]` (supports 10 and 9 players by removing the most advanced outfield slot, then re-spacing); `pressing_trigger(frame, team) -> bool` (back pass, poor touch, or receiver facing own goal). `runs_in_behind_rate(club_profile, role, opponent_line_height) -> float` (runs per minute in possession): rises with the team's directness and tempo, with runner roles (poacher, pressing forward, inside forward rather than target man) and pace, and with the **opponent's** line height (more space behind). These are team tactics, so they are not limited by the ±6% subtle cap; only the individual timing spread is. Offside frequency is never set directly: it emerges from runs × timing × the opponent's line.
- `Scenario(scenario_id, title, home_club_id, away_club_id, seed, beats: list[Beat])`, where `Beat(minute: float, kind: Literal["red_card","goal","sub","tactic_change","press_intensity","fatigue_spike"], team: Literal["home","away"], params: dict)`. Beats bias probabilities at their minute; they never teleport the state. `load_scenario(path) -> Scenario`.
- **Set pieces** (`engine/set_pieces.py`, the `set_piece` phase): `corner_delivery(...)` (in-swinger or out-swinger into the box, quality from the taker's `crossing`), then `aerial_duel(attacker, defender)` decided by `aerial` rating and height (keepers can claim), ending in a header with its own chance quality; `free_kick_option(...)` adds a direct shot option within about 30 m of goal (quality from `finishing`; walls lower it); `penalty(...)` for fouls inside the box (about 0.76 conversion, nudged by composure under the subtle cap, or the storyline cap in a beat). Shots carry `extras.set_piece ∈ {corner, free_kick, penalty}`, so stats can split set-piece and open-play goals.
- The 8 storylines: `comeback_red_card`, `press_collapse`, `keeper_heroics`, `late_sub_wins_it`, `derby_chaos`, `chess_match_0_0`, `underdog_low_block`, `counter_attack_masterclass`.

- [ ] **Step 1: Failing tests.**
  - `test_red_card_reshapes`: after a red-card beat, the team has 10 players in frames and `formation_shape(..., n_players=10)` is used.
  - `test_ten_men_stats_finite`: run the Task 6/7 functions on a frame after the red card → all finite. Task 12 adds its own 10-player test.
  - `test_beats_shift_outcome`: across 20 seeds, `comeback_red_card` gives the 10-man team a higher win rate than the unscripted control.
  - `test_fatigue_late`: the mean outfield top speed in minutes 80–90 is lower than in minutes 0–10.
  - `test_offsides_follow_tactics` (20 seeds): direct teams facing high lines average more offsides than possession teams facing deep lines.
  - `test_fouls_in_box_are_penalties`: a foul inside the penalty area restarts with a penalty (`extras.set_piece = "penalty"`); outside it, with a free kick.
  - `test_aerial_duel_follows_ratings`: across 1,000 duels, the higher `aerial` + height player wins more than 60%.
  - `test_set_piece_goal_share` (20 seeds): penalties average 0.2–0.4 per match, and set pieces produce 20–35% of goals (new `RANGES` entries).
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the module and storylines. Retrain xT with `scripts/train_xt.py --level 3 --seeds 300` and commit the grid.
- [ ] **Step 4: Run** the full suite plus the realism report at level 3 over 20 seeds. Expected: every check passes. Update `docs/realism.md`.
- [ ] **Step 5: Commit** `TASK-10: tactics, fatigue, scenarios; retrained xT`.

### Task 10.4: Season history simulated by the engine

**Files:** Create `src/matchmind/league/season.py`, `tests/league/test_season.py`.

**Interfaces:** `simulate_history(league, profiles, fixtures, rounds=9, tracking_hz=2, workers=os.cpu_count()) -> Season(results, standings, player_lines: list[PlayerMatchLine], milestones)`. It runs the real engine headless (2 Hz tracking, full events) in parallel processes. `PlayerMatchLine(match_id, round, player_id, club_id, minutes, passes, completed, forward_passes, progressive_passes, key_passes, xt_added, shots, shots_on_target, xg, dribbles, tackles, interceptions, pressures, fouls, distance_km, sprints, top_speed_ms, box_touches, goals, assists, yellow, red)`, computed by the same stat functions as live matches. `milestones_for(season, player_id | club_id) -> list[str]`. Suspensions from accumulated cards update `Discipline` before round 10.

- [ ] **Tests:** `test_history_deterministic`; `test_standings_match_results`; `test_player_lines_match_events` (one history match: line totals equal counts from its events); `test_runtime_budget` (rounds 1–9 complete in under 30 minutes on CI-sized hardware, or the timebox ruling applies: drop to `rounds=6`).
- [ ] **Commit** `TASK-10.4: engine-simulated season history`.

### Task 10.5: Effect tests (attributes really change the data)

**Files:** Create `tests/engine/test_effects.py` (marked `slow`, run in CI nightly and before release).

- [ ] **Tests (across ≥ 20 seeds each):** high-aggression teams foul more; disciplined, composed strikers are caught offside less often than impulsive ones in otherwise identical matches; high `press_intensity` gives lower PPDA; high-chemistry pairs complete more passes; `returning` players cover less distance after minute 60; home teams win 40–48% of matches; high `risk_tolerance` gives more progressive passes and lower completion; under storyline beats the targeted effect is at least 3× its subtle size.
- [ ] **Commit** `TASK-10.5: attribute effect tests`.

### Task 11: Pass quality, speed metrics, player alerts

**Files:** Create `src/matchmind/stats/passes.py`, `src/matchmind/stats/speed.py`, `tests/stats/test_passes.py`, `tests/stats/test_speed.py`.

**Interfaces:**
- `pass_quality(event, frame_at_t, xt_grid) -> PassQuality(distance_m, completed: bool, difficulty: float in [0,1], xt_added: float | None)`. `difficulty = sigmoid(w · [distance/40, defenders_within_3m_of_lane, receiver_pc_prob_inverse, lofted])` with fixed weights `w = (1.2, 0.8, 1.5, 0.4)` and bias `−1.6`.
- `player_accuracy(events, player_id, t_to) -> float`.
- `ball_speed(event) -> float | None` (from `ball_speed_ms`, else derived from the trajectory), `shot_speed_kmh(event) -> float`.
- `player_motion(frames, player_id, t_to) -> Motion(distance_m, top_speed_ms, sprints: int)`.
- `alerts(frames, t, thresholds=AlertThresholds(sprint_ms=7.0, sprint_min_s=1.0, distance_step_m=1000)) -> list[OverlayCue]` (`speed_alert` / `distance_alert` / `name_tag`).

- [ ] **Step 1: Failing tests.**
  - `test_difficulty_monotone_distance`: a longer pass in the same context is harder.
  - `test_edge_pass_finite`: a pass ending at `(105, 0)` → finite difficulty and xT.
  - `test_sprint_alert_fires_once`: a 3 s sprint fires 1 cue.
  - `test_distance_alert_each_km`.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the metrics and alerts.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `TASK-11: pass quality, speed metrics, alerts`.

### Task 12: Team metrics and key-moment triggers

**Files:** Create `src/matchmind/stats/team.py`, `src/matchmind/stats/moments.py`, `tests/stats/test_team.py`, `tests/stats/test_moments.py`.

**Interfaces:**
- `ppda(events, team_id, t_from, t_to) -> float` (opponent passes in their own 60% of the pitch ÷ team defensive actions there; returns `inf`-safe `None` when there are zero actions).
- `field_tilt(events, team_id, t_from, t_to) -> float` (share of final-third passes).
- `momentum_series(events, xt_grid, window_s=300, step_s=30) -> pd.DataFrame[t, home, away, diff]` (rolling xT-added plus shot xG proxy).
- `control_chaos(events, frames, t_from, t_to) -> float in [0,1]` (0 = control, 1 = chaos), built from turnover rate, mean possession length, pitch-control volatility, and direct-play share, each normalized by the `RANGES` midpoints.
- `detect_moments(match: MatchData, xt_grid: np.ndarray) -> list[Moment]` (computes the metrics it needs through the functions above) with rules: momentum `diff` changes sign and |Δ| > 0.08 within 5 min → `momentum_swing`; PPDA rises > 60% between consecutive 10-minute windows → `pressing_collapse`; mean player position changes from one formation template to another (nearest-template classifier) and stays changed for 3 min → `formation_shift`; shot with xG proxy > 0.25 → `big_chance`; 3 or more offsides against one team within 20 minutes → `offside_trap` (team level; add the literal to `MomentKind`); 3 or more corners for one team within 5 minutes → `corner_pressure` (team level; add the literal); goals, red cards. Moments closer than 60 s merge.

- [ ] **Step 1: Failing tests.**
  - `test_ppda_known_values`: a fixture of 20 opponent passes and 4 actions → 5.0.
  - `test_ppda_ten_men`: finite.
  - `test_control_chaos_extremes`: a fixture of long possessions → < 0.3; a fixture of a turnover every 3 events → > 0.7.
  - `test_detects_scripted_moments`: on the `press_collapse` seed, a `pressing_collapse` is detected within ±5 min of its beat; on `comeback_red_card`, a `red_card` moment is present.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the metrics and triggers.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `TASK-12: team metrics and moment detection`.

### Task 12.3: Season baselines and live discrepancies

**Files:** Create `src/matchmind/stats/baselines.py`, `src/matchmind/stats/deviations.py`, `tests/stats/test_baselines.py`, `tests/stats/test_deviations.py`; modify `schemas.py` (add `"player_deviation"` to `MomentKind`).

**Interfaces:**
- `player_baselines(season, profiles) -> dict[str, PlayerBaseline(player_id, minutes, per90: dict[str, float], dispersion: dict[str, float])]`. Per-90 rates are shrunk toward the player's role average with weight `minutes / (minutes + 450)`.
- `expected_at(baseline, stat, minutes_played, ctx) -> float` (per-90 rate × minutes ÷ 90, adjusted for team possession share against the season average and for red cards).
- `detect_deviations(match, baselines, t, stats=TRACKED_STATS) -> list[Deviation(player_id, stat, observed, expected, p_value, direction: under|over)]`, using a negative binomial (Poisson when dispersion ≈ 1). It flags only when `p < 0.01`, `minutes_played ≥ 30`, and `expected ≥ 5` (for "over", `observed ≥ 3`), and keeps the top 3 per 5-minute window by `−log p`. Each flagged deviation becomes a `Moment(kind="player_deviation", level="player", trigger_metric=stat, trigger_value=observed)` with `expected`, `baseline_per90`, and `p_value` in the store. `TRACKED_STATS` = the `PlayerMatchLine` count fields.

- [ ] **Tests:** `test_shrinkage` (a player with 90 minutes stays near the role mean; one with 810 minutes stays near their own rate); `test_example_forward_passes` (18 per 90, 3 observed at minute 60 → flagged "under", p < 0.01); `test_no_flag_early` (minute 20 → nothing); `test_false_alarm_rate` (on 20 unscripted seeds, at most 1 flag per team per match on average); `test_scripted_deviation_found` (the `press_collapse` storyline's targeted midfielder is flagged within 10 minutes of the beat).
- [ ] **Commit** `TASK-12.3: season baselines and discrepancy detection`.

### Task 13: Counterfactual scorer

**Files:** Create `src/matchmind/stats/counterfactual.py`, `tests/stats/test_counterfactual.py`.

**Interfaces:** Produces `counterfactual(event: Event, frame: TrackingFrame, xt_grid) -> Counterfactual(event_id, chosen: Option, best: Option, gain: float, alternatives: list[Option])`. It reuses `engine.decisions.enumerate_options` and `score_option`, so the scoring is literally the engine's.

- [ ] **Step 1: Failing tests.** `test_best_at_least_chosen` (`best.score >= chosen.score`); `test_matches_engine_extras` (for a level-3 event, `best.score` equals `event.extras["best_score"]` within 1e-9).
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the scorer.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `TASK-13: counterfactual scorer`.

### Task 14: Stats store and showcase match build

**Files:** Create `src/matchmind/store/db.py`, `src/matchmind/store/blob.py`, `src/matchmind/pipeline/build_match.py`, `tests/store/test_db.py`, `tests/pipeline/test_build_match.py`.

**Interfaces:** SQLAlchemy tables `matches`, `events`, `metrics` (`match_id, t, scope, scope_id, name, value`), `moments`, `insights`, `personalized`, `overlay_cues`, `agent_runs` (`run_id, agent, moment_id, status, attempts, latency_ms, trace_id, error`), and `season_*`. `Repo` methods: `save_match_data`, `get_events(match_id, t_from, t_to, types)`, `get_metric(match_id, name, scope, scope_id, t) -> float | None`, `save_moments`, `list_moments`, `save_insight`, `list_insights(match_id, persona, lang)`, `save_cues`, and `log_agent_run`. `blob.py`: `TrackingStore.write(match_id, frames)` / `read_window(match_id, period, t_from, t_to)`, backed by the local fs or Azure Blob (`adlfs`) depending on `Settings.blob_account_url`.

Metric materialization (`stats/metrics.py`), two paths over the same code:
- **Event-exact, on demand:** `metrics_at(match: MatchData, xt_grid, period, t, scope, scope_id) -> dict[str, float]` computes every team metric (Task 12) and player metric (Task 11) from events and frames **up to `t` only** (no look-ahead). It runs in milliseconds; pitch control is evaluated at the latest event before `t`, not on every frame. Agents and the Verifier use this path.
- **Stored snapshots:** `compute_metrics(match, xt_grid, step_s: float = 30, extra_times: list[tuple[Period, float]] = []) -> list[MetricRow(match_id, period, t, scope: Literal["team","player"], scope_id, name, value, kind: Literal["grid","moment"])]` stores `metrics_at` on a 30 s grid (for charts and the API) **plus one snapshot at each moment's `t_end`** (`kind="moment"`), so a moment's numbers are exactly the ones its insight cites.
- Per-event values (xT added, pass quality, chance quality) are stored per event, and per-frame values (speed, sprints) come from tracking. Neither waits for a snapshot.

CLI: `uv run matchmind build --scenario scenarios/comeback_red_card.yaml` runs simulate → per-event stats → moments → `compute_metrics(extra_times=moment end times)` → store. `matchmind build --all` builds all 8. Builds are idempotent: rebuilding a match replaces its rows.

- [ ] **Step 1: Failing tests.** `test_repo_roundtrip_sqlite_memory`; `test_get_metric_latest_before_t`; `test_build_match_end_to_end` (small scenario, 10 min match: moments > 0, metrics exist for both teams); `test_metrics_at_no_lookahead` (`metrics_at(match, …, t)` is identical when every event and frame after `t` is deleted); `test_snapshot_equals_metrics_at` (each stored grid and moment row equals `metrics_at` at its `t`); `test_every_moment_has_a_snapshot` (each moment's `t_end` has `kind="moment"` rows for both teams).
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the store and CLI. The SQL works on both SQLite and Azure SQL (no dialect-specific SQL; `pyodbc` driver extra for cloud).
- [ ] **Step 4: Run** the tests plus `matchmind build --all` (record the timing in the README).
- [ ] **Step 5: Commit** `TASK-14: stats store and match build CLI`.

### Task 15: MCP stats server

**Files:** Create `src/matchmind/mcp_server/server.py`, `tests/mcp_server/test_server.py`.

**Interfaces:** A FastMCP server named `matchmind-stats` with tools (all return JSON-serializable dicts and include `ref` strings for citation):
`get_match_summary(match_id)`, `get_events(match_id, period, t_from, t_to, types: list[str] | None)`, `get_team_metrics(match_id, team_id, period, t)`, `get_player_stats(match_id, player_id, period, t)`, `get_moment(moment_id)`, `get_counterfactual(event_id)`, `get_season_context(club_id | player_id)`, `get_metric(match_id, name, scope, scope_id, period, t)`, `get_player_profile(player_id)`, `get_club_profile(club_id)`, `get_player_baseline(player_id)`, `get_player_deviations(match_id, period, t)`. **Time-scoped tools are event-exact:** `get_team_metrics`, `get_player_stats`, `get_metric`, and `get_player_deviations` call `metrics_at` / `detect_deviations` with the match data up to the requested `t` (cached per `(match_id, period, t)`), instead of returning the latest 30 s row. They never return data from after `t`. Each result's `ref` is `"metric:<name>@<period>:<t>"`, which the Verifier recomputes with the same function. Produces `build_mcp(repo: Repo) -> FastMCP` and `mcp_app()` (streamable HTTP ASGI app mounted at `/mcp` in Task 21).

- [ ] **Step 1: Failing tests.** Use an in-memory MCP client session: `test_tools_listed` (12 names); `test_get_metric_matches_repo`; `test_unknown_match_returns_error_not_crash`; `test_team_metrics_event_exact` (at a `t` between two 30 s rows the tool returns `metrics_at(t)`, not the earlier row); `test_no_future_events` (`get_events` and the time-scoped tools never include anything after `t`).
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the server.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `TASK-15: MCP stats server`.

### Task 16: Agent runtime and locale-aware number checking

**Prerequisite (user):** an Azure for Students subscription, a Foundry project, a `gpt-4.1-mini` (or nearest mini) deployment, and `az login` done locally.

**Files:** Create `src/matchmind/agents/runtime.py`, `src/matchmind/agents/numbers.py`, `tests/agents/test_numbers.py`, `tests/agents/test_runtime.py`, `tests/fixtures/llm/`.

**Interfaces:**
- `runtime.py`: `make_chat_client(settings) -> ChatClientProtocol` (`agent_framework.foundry.FoundryChatClient` with `DefaultAzureCredential`. Use `FoundryChatClient`, not the preconfigured `FoundryAgent`, because tool choice must vary per request. Pin `agent-framework-*` versions in `pyproject.toml` and check the API names against the package README when implementing), `FakeChatClient(responses: dict[str, str] | Callable)` implementing the same protocol for tests, `make_agent(name: str, prompt_file: str, output_model: type[BaseModel], tools) -> Agent`, `stats_tools(settings) -> MCP tool` (Agent Framework MCP streamable HTTP tool pointed at `/mcp`), and `configure_tracing(settings)` (OpenTelemetry → Application Insights, one span per agent run with `moment_id` and `attempt`).
- `numbers.py`: `extract_numbers(text: str, lang: Lang) -> list[ExtractedNumber(value: float, span: tuple[int, int], unit: str | None)]`. It handles decimal comma (`es`, `pt`, `fr`), thousands separators, `%`, `km/h`, `m/s`, `km`, number words 0–20 in all 5 languages, and Arabic-Indic digits. Also `check_text(text, lang, claims: list[Claim], lookup: Callable[[Claim], float | None], rel_tol=0.01, abs_tol=0.05) -> NumberCheck(ok: bool, failures: list[str])`. Every extracted number must match some claim's verified value (minute marks and scorelines are allowed when they match the event times or score).

- [ ] **Step 1: Failing tests.**
  - `test_extract_es_decimal_comma`: `"1,5 km"` → 1.5 km.
  - `test_extract_fr_thousands`: `"12 000"` → 12000.
  - `test_extract_ar_digits`: `"١٢"` → 12.
  - `test_extract_word_numbers`: `"doce"` (es) → 12; `"onze"` (pt) → 11.
  - `test_check_flags_invented_number`.
  - `test_check_allows_minute_mark`.
  - `test_fake_client_structured_output` (FakeChatClient returns JSON parsed into the output model).
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the runtime and number checking.
- [ ] **Step 4: Run** the tests. Expected: PASS. Then a manual smoke: `uv run python -m matchmind.agents.runtime --ping` returns a reply from the Foundry deployment.
- [ ] **Step 5: Commit** `TASK-16: agent runtime and number verification`.

### Task 17: Tactical Analyst and Explainer agents

**Files:** Create `src/matchmind/agents/analyst.py`, `src/matchmind/agents/explainer.py`, `agents/prompts/analyst.v1.md`, `agents/prompts/explainer.v1.md`, `tests/agents/test_analyst.py`, `tests/agents/test_explainer.py`.

**Interfaces:**
- `async analyze(moments: list[Moment], client, tools) -> list[AnalystDecision(moment_id, surface: bool, level, priority: int 1–5, tactical_context: str, metrics_to_cite: list[str])]`. It receives a batch per 5 match-minutes and must call at least one MCP tool per surfaced moment.
- `async explain(decision: AnalystDecision, client, tools) -> Insight` (`source="agent"`, `verified=False`, with claims and event_ids filled in). Team and player levels get a "What should they do?" recommendation; game level gets "What to watch next". Every counterfactual claim cites `get_counterfactual`.

- [ ] **Step 1: Failing tests (FakeChatClient).** `test_analyst_filters_low_priority` (decisions with `surface=False` are not explained); `test_explainer_output_has_claims_and_refs` (every claim has a `ref`); `test_explainer_rejects_insight_without_event_ids` (a pydantic validation error triggers one regeneration).
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the agents and prompts. The prompts state Constitution I and II verbatim and include 2 worked examples.
- [ ] **Step 4: Run** the tests. Expected: PASS. A live smoke on 3 moments from `comeback_red_card` is written to `tests/fixtures/llm/` as recorded fixtures.
- [ ] **Step 5: Commit** `TASK-17: analyst and explainer agents`.

### Task 18: Verifier agent and regeneration loop

**Files:** Create `src/matchmind/agents/verifier.py`, `agents/prompts/verifier.v1.md`, `tests/agents/test_verifier.py`, `evals/verifier_golden.jsonl`, `scripts/run_foundry_eval.py`.

**Interfaces:** `async verify(insight: Insight, lang: Lang, text: str, repo: Repo, client) -> Verdict(ok: bool, failures: list[str], fixed_claims: list[Claim])`. Order: (1) deterministic `numbers.check_text` against `repo` values (authoritative, cannot be overridden); (2) the agent checks qualitative claims against the cited events (for example "pressed high" vs event locations). `ok` requires both.

- [ ] **Step 1: Failing tests.** `test_deterministic_failure_cannot_be_overridden` (the fake LLM says OK, the number check fails → `ok=False`); `test_passes_correct_insight`; `test_failures_are_actionable` (each failure names the claim and the correct value).
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the verifier. Golden set: 40 insights (20 correct, 20 with planted errors).
- [ ] **Step 4: Run** the tests. Expected: PASS. Run the Foundry evaluation with `scripts/run_foundry_eval.py` on the golden set; record precision and recall in `docs/evals.md` (target recall ≥ 0.95 on planted errors).
- [ ] **Step 5: Commit** `TASK-18: verifier agent and evals`.

### Task 19: Narrative and Personalization agents (4 personas, 5 languages)

**Files:** Create `src/matchmind/agents/narrative.py`, `src/matchmind/agents/personalizer.py`, `src/matchmind/agents/templates.py`, prompts `narrative.v1.md` and `personalizer.v1.md`, and tests.

**Interfaces:**
- `async live_line(insight: Insight, season_ctx, client) -> str` (≤ 140 characters), `async recap(match_id, insights, repo, client) -> Recap(title, paragraphs: list[str], key_numbers: list[Claim])`.
- `async personalize_batch(insight: Insight, lang: Lang, variants: list[Variant], client) -> list[PersonalizedText]`: one model call per (insight, language) returns all variants, to save tokens and quota. `variants_for(insight, meta) -> list[Variant]` returns `analyst`, `casual`, `club_fan` for each of the 2 clubs, and `player_focus` only for players named in the insight's claims or `player_id`. For any other favorite player, the UI uses the `player_focus` template.
- Persona rules: `analyst` ≤ 90 words, includes metric names and values; `casual` ≤ 45 words, no jargon (blocklist `["xT","PPDA","field tilt","pitch control"]` must be replaced by plain words); `club_fan` written from the favorite club's side; `player_focus` centred on the favorite player.
- `templates.render(insight, persona, lang) -> PersonalizedText` gives deterministic fallback text in all 5 languages from the claims alone.

- [ ] **Step 1: Failing tests.**
  - `test_casual_has_no_jargon`.
  - `test_word_limits`.
  - `test_template_all_langs` (5 languages × 4 personas non-empty, and `numbers.check_text` passes on each).
  - `test_arabic_template_rtl_marker` (the payload carries `dir="rtl"`).
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the agents and templates. Native generation for all 5 languages; Azure AI Translator is not used in phase 1.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `TASK-19: narrative and personalization agents`.

### Task 20: Orchestrator workflow, retries, precomputed replays

**Files:** Create `src/matchmind/agents/orchestrator.py`, `tests/agents/test_orchestrator.py`, `scripts/precompute.py`.

**Interfaces:** `async run_window(match_id, period, t_from, t_to, deps: Deps) -> WindowReport` and `async run_match(match_id, deps, personas=ALL, langs=ALL) -> PipelineReport(insights: int, verified: int, templated: int, agent_runs: int, p95_latency_ms: float)`. `Deps(repo, client, tools, clock)`.

The workflow is an Agent Framework graph (`WorkflowBuilder` from `agent-framework-core`; orchestration builders from `agent-framework-orchestrations` where they fit): Analyst → (fan-out per surfaced moment) Explainer → Verifier ⟲ (max 2 regenerations, feeding failures back) → Narrative → `personalize_batch` per language → Verifier (lang). `scripts/devui.py` launches Agent Framework DevUI locally to visualize the workflow (dev only, used for the video). Precompute is resumable (skips rows that are already verified) and throttled to the deployment's TPM quota (`--tpm`). Retry policy: timeouts and 429s use exponential backoff (1 s, 2 s, 4 s; max 3), then template fallback. Each step writes `agent_runs` and the shared state in `repo`. Precompute writes everything for a match, plus `replay_manifest.json` (seed, engine_version, model deployment, prompt versions).

- [ ] **Step 1: Failing tests (FakeChatClient).**
  - `test_happy_path_all_verified`.
  - `test_verifier_rejection_triggers_regeneration` (the first Explainer answer is wrong, the second is right → 1 regeneration, final `verified=True`).
  - `test_persistent_failure_falls_back_to_template` (`source="template"`, the UI-visible count is unchanged).
  - `test_429_backoff_then_success`.
  - `test_malformed_json_retry`.
  - `test_agent_runs_logged`.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the orchestrator.
- [ ] **Step 4: Run** the tests. Expected: PASS. Then `uv run python scripts/precompute.py --all` against Foundry; record the token and cost estimate per match in `docs/costs.md`.
- [ ] **Step 5: Commit** `TASK-20: orchestrator, retries, precompute`.

### Task 21: API service (REST + SSE live replay + MCP mount)

**Files:** Create `src/matchmind/api/app.py`, `routes_matches.py`, `routes_insights.py`, `routes_live.py`, `ratelimit.py`, and `tests/api/*`.

**Interfaces (the frontend relies on these exactly):**
- `GET /api/health` → `{"ok": true, "version": str}`
- `GET /api/matches` → `list[{match_id, title, home, away, score, scenario_id}]`
- `GET /api/matches/{id}` → `MatchMeta` + final score + `realism` report
- `GET /api/matches/{id}/tracking?period=&from=&to=` → `{frames: [...]}` (max 60 s per call)
- `GET /api/matches/{id}/timeline` → `{moments: list[Moment], momentum: [{t, home, away}]}`
- `GET /api/matches/{id}/insights?persona=&lang=` → `list[{insight, text: PersonalizedText}]`
- `GET /api/insights/{id}/why` → `{claims, events, agent_runs, trace_id, counterfactual: Counterfactual | None}`
- `GET /api/matches/{id}/stats?scope=team|player&scope_id=&period=&t=` → `{metrics: {name: value}, baseline: {name: expected_at_t} | null, profile: PlayerProfile | ClubProfile}` (feeds the Team and Player tabs, including "vs season average")
- `GET /api/matches/{id}/pitch-control?period=&t=` → `{grid: number[21][32], attacking_team}` (heatmap overlay and freeze-frames)
- `GET /api/matches/{id}/recap?lang=&persona=` → `Recap`
- `GET /api/league` → `{clubs, players}` (for picking favorites)
- `GET /api/matches/{id}/live?period=&from_t=&speed=` → SSE stream. Event types are `frame` (5 Hz downsampled), `event`, `cue` (OverlayCue), `insight`, and `end`. Each message has a monotonically increasing `id` = `f"{period}:{t:.1f}:{seq}"`; reconnecting with `Last-Event-ID` or `from_t` resumes with no duplicates.
- `POST /api/matches/{id}/regenerate` body `{moment_id, persona, lang}` → a live agent run. Rate limit: 5 per hour per IP and 100 per day globally; returns 429 with a `retry_after` JSON field.
- `/mcp` → the MCP app from Task 15.

- [ ] **Step 1: Failing tests (httpx AsyncClient).**
  - `test_matches_list`.
  - `test_tracking_window_cap`.
  - `test_sse_order_and_types`.
  - `test_sse_resume_no_duplicates` (read to t = 120, reconnect with `from_t=120` → the first new id > the last old id, and the union of ids has no duplicates or gaps in `seq`).
  - `test_sse_seek_backwards` (`from_t=30` after 120 → resends from 30 with a new stream).
  - `test_regenerate_rate_limited` (6th call → 429).
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the API. Fast lane: cues are emitted at their `t_in` from precomputed data, independent of the agents. CORS allows only the Static Web App origin and `localhost:5173`. All query params are validated by pydantic (unknown persona or lang → 422).
- [ ] **Step 4: Run** the tests. Expected: PASS. Then `uv run uvicorn matchmind.api.app:app` and `curl -N localhost:8000/api/matches/<id>/live` shows events.
- [ ] **Step 5: Commit** `TASK-21: API with SSE replay and rate limits`.

### Task 22: Visual direction (two mockups, user picks one)

**Files:** Create `web/` (Vite React TS + Tailwind scaffold), `web/src/design/tokens.css`, `web/mockups/broadcast-dark.html`, `web/mockups/editorial-light.html`, `docs/design.md`.

**Interfaces:** Produces design tokens as CSS variables (`--mm-bg`, `--mm-surface`, `--mm-text`, `--mm-accent`, `--mm-home`, `--mm-away`, `--mm-good`, `--mm-warn`, font stack, spacing scale) that every component in Task 23 uses. Both mockups show the same screen: pitch, Game / Team / Player tabs, a moment timeline, an insight card, and the persona and language switcher.

- [ ] **Step 1:** Use the frontend-design skill to produce both mockups, with WCAG AA contrast checked (axe or a contrast script; record the results in `docs/design.md`).
- [ ] **Step 2:** **User checkpoint:** the user picks a direction (or a mix). Write the choice into `docs/design.md` and `tokens.css`.
- [ ] **Step 3: Commit** `TASK-22: visual direction and design tokens`.

> **As built (2026-10-26):** executed through the detailed plan `docs/superpowers/plans/2026-10-26-frontend.md` (design: `docs/superpowers/specs/2026-10-26-frontend-visual-direction-design.md`). The user chose broadcast-dark and asked for two switches (Team ⇄ Player, Fan ⇄ Scout) instead of persona pills; the welcome page (TASK-23.7), Best Plays tab (23.8), live re-ask, and a model-free seeded demo match for browser tests were added. A final review found accent colors unreadable for 5 clubs, among 8 fixed issues.

### Task 23: Frontend app

**Files:** Create `web/src/` (`api/client.ts`, `state/store.ts` (Zustand), `components/Pitch.tsx` (canvas, 60 fps interpolation between 5 Hz frames), `Overlays.tsx`, `Timeline.tsx`, `InsightCard.tsx`, `AskWhyPanel.tsx`, `PersonaBar.tsx`, `MatchPicker.tsx`, `RealismPanel.tsx`, `i18n/*.json` for 5 languages, `pages/Match.tsx`), `web/tests/*.test.tsx`, `web/e2e/smoke.spec.ts`.

**Interfaces:** Consumes the Task 21 endpoints exactly. Prefs are stored in `localStorage` (wrapped in try/catch): `{persona, lang, favorite_club_id, favorite_player_id}`. `dir="rtl"` on `<html>` when `lang === "ar"`.

- [ ] **Step 1: Failing tests (Vitest + Testing Library).**
  - `Timeline` renders one marker per moment, and clicking one calls `seek(t)`.
  - `InsightCard` shows a confidence label and an "Ask why" button.
  - `PersonaBar` switching language refetches insights with `lang`.
  - Arabic sets `dir="rtl"`.
  - `Overlays` never shows more than 3 simultaneous cues (highest priority wins).
- [ ] **Step 2: Run** `cd web && npm test`. Expected: FAIL.
- [ ] **Step 3: Implement** the components following the tokens and the frontend-design skill. Responsive down to 375 px; full keyboard navigation.
- [ ] **Step 4: Run** `npm test` plus `npx playwright test` (smoke: open a match, play 10 s, an insight appears, switch to Spanish, open Ask why). Expected: PASS. Add the web job to CI.
- [ ] **Step 5: Commit** `TASK-23: frontend app`.

### Task 24: Azure infrastructure and deployment

**Files:** Create `azure.yaml` (azd), `infra/main.bicep`, `infra/main.parameters.json`, `infra/modules/{containerapp,sql,storage,monitoring,staticweb}.bicep`, `Dockerfile`, `.github/workflows/deploy.yml`, `docs/deploy.md`. Deployment uses `azd up`, and `azd pipeline config` sets up GitHub OIDC. Module layout follows `Azure-Samples/azure-ai-travel-agents` (MIT), used as a reference only; any copied module keeps its MIT header and is listed in `THIRD_PARTY_NOTICES.md`.

**Interfaces:** Resources: Log Analytics + Application Insights; Storage account (tracking blobs); Azure SQL (serverless, free offer); a Container Apps environment and one app `matchmind-api` (min replicas 0 by default, 1 during judging if the budget allows; the system-assigned managed identity gets the Cognitive Services OpenAI User role on the Foundry resource, plus SQL and Blob data roles); Static Web App (free) for `web/` with `/api` proxied to the container app. Deploy uses GitHub OIDC federated credentials (no stored secrets), and the budget resource has alerts at $25 and $50.

- [ ] **Step 1:** `az bicep build infra/main.bicep` and `az deployment group what-if` succeed.
- [ ] **Step 2:** Deploy. Seed the cloud DB and blobs with the precomputed replays (`matchmind build --all --target cloud`, `precompute --all --target cloud`).
- [ ] **Step 3: Verify** that `curl https://<api>/api/health` returns `ok`, the Static Web App URL loads, a replay plays, and App Insights shows agent spans from a `regenerate` call.
- [ ] **Step 4: Commit** `TASK-24: Azure infra and deploy pipeline`.

**As built (2026-10-27), and why it differs:**
- **No Static Web App:** Azure for Students allows five regions and Static Web Apps is offered in none of them, so the API container also serves the website (one URL, no CORS).
- **Azure SQL on Basic in Canada Central**, not serverless free in North Central US: the free tier auto-pauses (a minute's wait for the first judge after an idle hour; keeping it awake costs about $190 a month), and North Central US then refused new SQL servers (`RegionDoesNotAllowProvisioning`).
- **One user-assigned managed identity** instead of the system-assigned one: it must exist before the app to pull images and sign in to SQL (an Entra token per connection; `store/db.py` `make_engine`).
- **Images built by GitHub Actions and pulled from GitHub Container Registry (public)**, not built in Azure: ACR Tasks (`az acr build`, azd remote build) are paused on free-credit subscriptions, and local Docker Desktop froze. `azd deploy` is not used; the template takes the image as a parameter (`apiImage`).
- **Seeding** is `scripts/seed_cloud.py` (copy the local database to Azure SQL, grant the identity, upload tracking files), not `--target cloud` flags.
- **Deploy workflow** updates the app's image after each image build, signing in with GitHub OIDC; it waits for a one-time Entra app registration (TASK-24.2 left open).

**Roadblocks, in order:** the App Insights connection string was first entered as a bare key; Docker Desktop's engine froze (a local build hung for 41 minutes and later blocked `azd up` at `docker ps`); SQL capacity in North Central US; the container app lost its registry setting and couldn't pull from ACR; ACR builds unavailable; on the Mac seeding side, the ODBC driver install, `Trusted_Connection` conflicting with token sign-in (FA005), the driver finding OpenSSL 4 instead of 3, and a 96-character column too narrow for batched Analyst runs (231). Each fix is in the changelog and `wiki/infra-ops.md`.

### Task 25: Local run, docs, architecture

**Files:** Create `docker-compose.yml` (api + web; SQLite; no Azure needed for replays) and `docs/architecture.md` (diagram); modify `README.md` (pitch, features mapped to hackathon requirements, quick start, test URL, judge instructions, credits and licenses, realism and eval results, costs).

- [ ] **Step 1:** On a fresh clone, `docker compose up` serves the app at `localhost:5173` with all 8 replays (verified from a clean directory).
- [ ] **Step 2:** The README requirement table maps every §4.1 item to code paths.
- [ ] **Step 3: Commit** `TASK-25: local run and documentation`.

---

## Phase 2: Additions after the core is polished (Tasks 26–30, 32–34)

Suggested priority: 34 Backstory + vector search → 26 Scenario Designer → 27 Ingest (multi-agent recovery story) → 33 MCP tool (Copilot demo) → 28 Overlay Director → 32 kloppy export → 29 streaming → 30 voice.

### Task 34: Backstory agent and vector search (Phase 2, first priority)

**Interfaces:** `async write_backstory(profile, transfers, legends_ctx, client) -> Backstory(player_id, text, claims)`: 2–3 sentences that use only profile fields, checked by the Verifier (no new numbers). Embeddings come from a Foundry `text-embedding-3-small` deployment (new user setup step) and are stored in an Azure SQL `VECTOR(1536)` column (fallback: in-process cosine search over at most 400 rows if the free tier lacks vector support). MCP tool `search_backstories(query, k=5)`, used by the Narrative agent, the Scenario Designer, and an "Ask MatchMind" box.

- [ ] **Tests:** every backstory passes the Verifier; `search_backstories("striker back from injury facing his old club")` returns a player with those flags in the top 5 (fixture embeddings in tests).
- [ ] **Commit** `TASK-34: backstory agent and vector search`.

### Task 26: Scenario Designer agent and "Make a match" UI

**Interfaces:** `async design_scenario(prompt: str, league: League, client) -> Scenario` (validated by the pydantic schema; unknown clubs are rejected), then `POST /api/scenarios {prompt}` → a job id; the job runs build → realism validate (rejected and retried once if it fails) → orchestrator → the new match appears in the list. Rate limit: 3 per hour per IP and 20 per day globally.

- [ ] **Tests:** `test_prompt_to_valid_scenario` (fake client); `test_invalid_club_rejected`; `test_realism_gate_rejects_and_retries`; frontend `MakeMatch` form submits and shows progress.
- [ ] **Commit** `TASK-26: scenario designer agent`.

### Task 27: Ingest agent and failure-recovery demo

**Interfaces:** `replay/streamer.py` with `stream(match_id, faults: FaultPlan | None)` injecting gaps, duplicates, and out-of-range coordinates. `agents/ingest.py` has a deterministic detector (sequence gaps, duplicate ids, coordinates out of bounds, non-monotonic t) that triggers `async decide_recovery(anomaly, client) -> Literal["replay_window","interpolate","drop","fallback_baseline"]`, applied by code. A "Chaos mode" toggle in the UI shows recovery live, with a banner.

- [ ] **Tests:** each fault type detected; recovery leaves the stats identical to the clean run (for `replay_window`); UI banner appears.
- [ ] **Commit** `TASK-27: ingest agent and fault injection`.

### Task 28: Overlay Director agent and broadcast JSON

**Interfaces:** `async direct(cues: list[OverlayCue], insights, t, client) -> list[OverlayCue]`. Hard rules are enforced in code after the agent: ≤ 3 visible cues; insight cards last 6–12 s; no overlap with a freeze-frame. Output follows the published `docs/overlay-schema.json` (JSON Schema), with `GET /api/matches/{id}/overlays.json` for broadcast systems.

- [ ] **Tests:** constraint enforcement; schema validation of the output; deterministic fallback when the agent fails.
- [ ] **Commit** `TASK-28: overlay director and broadcast schema`.

### Task 29: Streaming mode (Event Hubs + Functions)

**Interfaces:** `matchmind stream --to eventhub` publishes events; an Azure Function (Python v2, Event Hubs trigger) writes to Azure SQL and calls `run_window` every 5 match-minutes. Turned on by `MATCHMIND_STREAMING=1`; the replay path stays the default.

- [ ] **Tests:** the Function handler unit test with a fake binding; a local end-to-end run with the Event Hubs emulator.
- [ ] **Commit** `TASK-29: streaming mode via Event Hubs and Functions`.

### Task 30: Voice commentary (optional)

**Interfaces:** Azure AI Speech neural TTS for `live_line` in the 5 languages, cached as MP3 in Blob; UI mute toggle (off by default).

- [ ] **Tests:** cache hit/miss; language-to-voice mapping.
- [ ] **Commit** `TASK-30: voice commentary`.

---

### Task 32: Standard-format export with kloppy (interoperability)

**Interfaces:** `export/kloppy_export.py`: `to_kloppy_tracking(data: MatchData) -> kloppy.domain.TrackingDataset` and `to_kloppy_events(data) -> kloppy.domain.EventDataset`. CLI `matchmind export --format kloppy|csv --match <id>`. This lets any PySport tool (kloppy, mplsoccer, databallpy, floodlight) load MatchMind's synthetic data, which supports the data-innovation and enterprise stories.

- [ ] **Tests:** round trip through kloppy `to_df()` keeps the frame count, player count, and pass count; coordinates map to kloppy's pitch dimensions.
- [ ] **Commit** `TASK-32: kloppy export`.

### Task 33: MatchMind as an MCP tool for other agents

**Interfaces:** `agent-framework-hosting-mcp` `WorkflowMCPTool` wraps the analysis workflow from Task 20 as an MCP tool `matchmind.analyze_moment(match_id, t, persona, lang)`, served next to the stats tools at `/mcp`. Demo: GitHub Copilot Agent Mode (a judged hero technology) asks MatchMind about a moment from VS Code.

- [ ] **Tests:** the MCP client lists the tool; a FakeChatClient-backed call returns a verified `PersonalizedText`.
- [ ] **Commit** `TASK-33: expose workflow as MCP tool`.

## Phase 3: Submission (Task 31)

### Task 31: Submission package

- [ ] Capture app footage with a Playwright script (`web/e2e/record_demo.spec.ts`, 1920×1080 video) so takes are repeatable.
- [ ] Demo video under 2:00, royalty-free audio, no third-party marks. Script in `docs/video-script.md`: problem (0:00–0:15), live match with overlays (0:15–0:45), persona and language switch (0:45–1:05), Ask why and the verifier catching an error (1:05–1:25), multi-agent recovery (1:25–1:45), architecture and close (1:45–1:58). Uploaded to YouTube (unlisted is fine) or another platform the rules allow.
- [ ] Elevator pitch (what, Microsoft tech used, problem solved) and judge testing instructions in the README and on the Hackathon Website.
- [ ] Final checks: the repo is public, CI is green, the test URL works from a private browser window, the budget forecast covers the deployment through 2026-11-10, and the submission is made before 2026-10-27 11:59 pm PT.
- [ ] **Commit** `TASK-31: submission materials`.
