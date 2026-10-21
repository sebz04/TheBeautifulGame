# MatchMind Tasks

This file tracks all work for the MatchMind project. Each task maps to the matching section of the implementation plan (`docs/superpowers/plans/2026-10-21-matchmind.md`) and must follow `CONSTITUTION.md`. Large tasks are split into sub-tasks (`TASK-N.M`), each sized at half a day or less with its own tests and commit. Move a sub-task to **In Progress** when work starts and to **Done** once it meets the Definition of Done. A parent task is done when all of its sub-tasks are done.

## Definition of Done

A task or sub-task moves to Done only when all of these are true:

- All of its acceptance criteria are met.
- Tests pass locally and CI is green on `main`.
- Changes are committed with the task ID at the start of the message (for example `TASK-4.2: level-1 baseline engine`), and the commit hash is recorded on its `Commit:` line.
- The wiki is updated in the same commit (TASK-0).
- No secrets, real club or player names, real match data, or third-party trademarks were added.

## To Do

### Standing

**TASK-0:** Keep `wiki/` current with every code change, so any session can learn the codebase from the wiki instead of re-reading the code. This task never moves to Done; it is checked on every commit.
- [ ] Every commit touching `src/` or `web/src/` also updates the affected wiki pages, the module map in `wiki/README.md`, and one line in `wiki/changelog.md`
- [ ] Every wiki page stays at 150 lines or fewer and describes what exists now
- [ ] `scripts/check_wiki.py` enforces both rules in CI and as a pre-commit hook (from TASK-1.3)

Commit: (per commit; see `wiki/changelog.md`)

### Phase 1: Core pipeline

#### TASK-1: Repo scaffold, tooling, CI

**TASK-1.1:** Set up the uv project, package layout, settings, and the first tests.
- [ ] `uv run pytest`, `ruff check .`, and `mypy src` pass locally
- [ ] `.env` and `data/` are git-ignored and `.env.example` lists every key with no values

Commit:

**TASK-1.2:** Add GitHub Actions CI with a dependency license gate and `THIRD_PARTY_NOTICES.md`.
- [ ] CI runs lint, types, tests, and `scripts/check_licenses.py` on every push and PR, and is green
- [ ] The license gate fails on a dependency whose license is not on the allowlist

Commit:

**TASK-1.3:** Add `scripts/check_wiki.py` with a pre-commit hook and CI step.
- [ ] Fails when `src/` changes without a `wiki/` change, or when a wiki page is over 150 lines
- [ ] Runs in CI and through pre-commit

Commit:

#### TASK-2: Shared schemas and pitch geometry

**TASK-2:** Define every shared pydantic model and the pitch geometry helpers.
- [ ] Every model in plan Task 2 exists (including `added_time_s`, `Variant`, and the `PersonalizedText` club/player fields) and round-trips through JSON
- [ ] `zone_index` maps edge and out-of-bounds coordinates inside the grid

Commit:

#### TASK-3: Fictional league

**TASK-3:** Generate the fictional 10-club league, squads, and season history with milestones.
- [ ] The same seed gives an identical league (10 clubs × 20 players, unique IDs and shirt numbers)
- [ ] No name matches the real-club or real-player blocklists
- [ ] `milestones_for` returns the next milestone (for example `goals:10`)

Commit:

#### TASK-4: Level-1 engine

**TASK-4.1:** Implement match Parquet/JSON I/O (`write_match` / `read_match`).
- [ ] A round trip keeps events, frames, and meta identical

Commit:

**TASK-4.2:** Build the formation-anchored baseline simulation (level 1).
- [ ] The same seed gives identical events
- [ ] Completed passes agree with tracking (passer within 1.5 m, receiver within 2.0 m)
- [ ] The frame count matches both halves plus added time at 0.1 s spacing

Commit:

#### TASK-5: Realism validator

**TASK-5:** Add the realism validator and the level-1 baseline report.
- [ ] `validate_match` flags out-of-range metrics
- [ ] `docs/realism.md` contains the level-1 report over 20 seeds

Commit:

#### TASK-6: Pitch control

**TASK-6:** Implement vectorized pitch control with a parity test against the Friends of Tracking reference.
- [ ] Symmetry, lone-attacker, 10 v 11, and edge-target tests pass
- [ ] Matches the vendored reference within 0.02 per cell
- [ ] A 32×21 grid computes in under 50 ms

Commit:

#### TASK-7: xT

**TASK-7:** Train xT on synthetic events and commit the grid.
- [ ] Values are in [0, 1], increase toward goal, and are finite at the pitch edges
- [ ] `data/models/xt_grid.npy` is produced by `scripts/train_xt.py`

Commit:

#### TASK-8: Level-2 players

**TASK-8.1:** Add player kinematics: speed and acceleration caps and fatigue.
- [ ] Speed and acceleration never exceed their caps
- [ ] Low energy reduces top speed

Commit:

**TASK-8.2:** Add role targets: mark, press, cover, support, run in behind, hold the line, goalkeeper.
- [ ] Each role gives a sensible target in fixture situations
- [ ] The defensive line holds within 1.5 m

Commit:

#### TASK-9: Level-3 coupled engine

**TASK-9.1:** Implement ball flight physics for ground, lofted, and shot trajectories.
- [ ] A 30 m ground pass at 15 m/s takes 2.0–2.6 s
- [ ] Pass and shot speeds fall within their configured ranges

Commit:

**TASK-9.2:** Implement on-ball option enumeration, scoring, and skill-weighted choice.
- [ ] Skill 0.95 picks the best option > 70% of the time; skill 0.2 picks it < 45%
- [ ] `chosen_score`, `best_score`, and `best_option` are written to `Event.extras`

Commit:

**TASK-9.3:** Build the 10 Hz event-coupled loop and tune constants (3-hour timebox).
- [ ] Events and tracking stay consistent and deterministic at level 3
- [ ] The realism report passes every check except goals per match, or the remaining deviations are recorded in `docs/realism.md`

Commit:

#### TASK-10: Level-4 tactics and scenarios

**TASK-10.1:** Add phase-dependent formation shapes and pressing triggers, including 10 and 9 players.
- [ ] Shapes work for 11, 10, and 9 players
- [ ] Pressing triggers fire on back passes and poor touches in fixtures

Commit:

**TASK-10.2:** Add the scenario schema, storyline beats, and late-game fatigue.
- [ ] A red-card beat removes a player and reshapes the team, and stats stay finite
- [ ] Top speed in minutes 80–90 is lower than in minutes 0–10

Commit:

**TASK-10.3:** Write the 8 storyline YAMLs, retrain xT, and pass the full realism report.
- [ ] Scripted beats measurably shift outcomes across 20 seeds
- [ ] The full realism report passes at level 3 over 20 seeds (or deviations are documented)

Commit:

#### TASK-11: Player metrics

**TASK-11.1:** Compute pass distance, accuracy, difficulty, and xT added.
- [ ] Difficulty increases with distance and is finite at the pitch edges

Commit:

**TASK-11.2:** Compute ball and shot speed, distance, and sprints, plus the alert and name-tag cues.
- [ ] Sprint and distance alerts fire exactly once per trigger
- [ ] Distance and speed agree with the databallpy/floodlight cross-check within 2%

Commit:

#### TASK-12: Team metrics and moments

**TASK-12.1:** Compute PPDA, field tilt, momentum, and control vs. chaos.
- [ ] Known-value fixtures match (PPDA = 5.0, control/chaos extremes)
- [ ] All metrics are finite with 10 players

Commit:

**TASK-12.2:** Implement the key-moment rule triggers with merging.
- [ ] Scripted pressing collapses and red cards are detected in their scenarios
- [ ] Moments less than 60 s apart are merged

Commit:

#### TASK-13: Counterfactuals

**TASK-13:** Score counterfactual passes using the engine's own option scoring.
- [ ] The best option scores at least as high as the chosen one and equals the engine's `best_score`

Commit:

#### TASK-14: Store and build

**TASK-14.1:** Build the SQLAlchemy store and repository (SQLite locally, Azure SQL compatible).
- [ ] Repo round-trip and latest-metric-before-t tests pass

Commit:

**TASK-14.2:** Build the tracking store (local Parquet or Azure Blob) with windowed reads.
- [ ] `read_window` returns exactly the requested frames

Commit:

**TASK-14.3:** Add metric materialization and the idempotent `matchmind build` CLI.
- [ ] `matchmind build --all` produces 8 matches with moments and metrics
- [ ] Rebuilding a match replaces its rows instead of duplicating them

Commit:

#### TASK-15: MCP server

**TASK-15:** Expose the stats store as an MCP server with 8 tools.
- [ ] All 8 tools are listed and return values that match the repo
- [ ] Unknown IDs return an error, not a crash

Commit:

#### TASK-16: Agent runtime

**TASK-16.1 (user, start now):** Set up Azure for Students, budget alerts, a Foundry project, and a `gpt-4.1-mini` deployment.
- [ ] The subscription is active with budget alerts at $25 and $50
- [ ] The Foundry deployment exists and its TPM quota is recorded in `wiki/infra-ops.md`

Commit:

**TASK-16.2:** Implement locale-aware number extraction and claim checking.
- [ ] Handles decimal commas, thousands separators, number words, and Arabic-Indic digits in all 5 languages
- [ ] Flags invented numbers and allows valid minute marks and scorelines

Commit:

**TASK-16.3:** Build the Foundry chat client factory, `FakeChatClient`, MCP tool wiring, and Application Insights tracing.
- [ ] A live ping to the Foundry deployment succeeds
- [ ] Agent runs emit spans with `moment_id` and `attempt`

Commit:

#### TASK-17: Analyst and Explainer

**TASK-17.1:** Build the Tactical Analyst agent and its prompt.
- [ ] Only moments with `surface=True` move on, and each surfaced moment uses at least one MCP call

Commit:

**TASK-17.2:** Build the Explainer agent with claims, refs, and recommendations.
- [ ] Every insight has claims with refs and event IDs
- [ ] Recorded live fixtures exist for 3 moments

Commit:

#### TASK-18: Verifier

**TASK-18.1:** Build the Verifier agent: a deterministic number gate, then a qualitative check.
- [ ] A deterministic failure can never be overridden by the model
- [ ] Each failure names the claim and the correct value

Commit:

**TASK-18.2:** Build the golden eval set (40 insights) and run the Foundry evaluation.
- [ ] Recall on planted errors is at least 0.95 and recorded in `docs/evals.md`

Commit:

#### TASK-19: Narrative and personalization

**TASK-19.1:** Write the deterministic fallback templates for 4 personas × 5 languages.
- [ ] Every combination renders and passes the number check, and Arabic carries `dir="rtl"`

Commit:

**TASK-19.2:** Build the Narrative agent (live lines up to 140 characters, full-time recap with milestones).
- [ ] Live lines respect the length limit and every recap number is a cited claim

Commit:

**TASK-19.3:** Build batched personalization (`personalize_batch` and `variants_for`).
- [ ] One call per (insight, language) returns every variant
- [ ] Casual text contains no jargon, and every persona respects its word limit

Commit:

#### TASK-20: Orchestration

**TASK-20.1:** Build the Agent Framework workflow with regeneration, backoff, template fallback, and run logging.
- [ ] Rejection → regeneration, 429 → backoff, malformed JSON → retry, and persistent failure → template are all covered by tests
- [ ] Every step writes an `agent_runs` row

Commit:

**TASK-20.2:** Add resumable, throttled precompute with replay manifests and a cost report, plus the DevUI launcher.
- [ ] All 8 matches are precomputed, and a re-run skips rows that are already verified
- [ ] Token use and cost per match are recorded in `docs/costs.md`

Commit:

#### TASK-21: API

**TASK-21.1:** Add the read endpoints: matches, tracking, timeline, insights, why, stats, pitch control, recap, league.
- [ ] Each endpoint matches the plan's contract, and unknown persona or language returns 422

Commit:

**TASK-21.2:** Add SSE live replay with resume and seek.
- [ ] Resume and seek produce no duplicate or missing messages
- [ ] Fast-lane cues arrive within 1 s of their `t_in` in replay

Commit:

**TASK-21.3:** Add the regenerate endpoint with rate limits, the `/mcp` mount, and CORS.
- [ ] The 6th regenerate call in an hour returns 429 with `retry_after`
- [ ] CORS allows only the Static Web App origin and localhost

Commit:

#### TASK-22: Visual direction

**TASK-22 (user checkpoint):** Create two mockups (broadcast-dark and editorial-light) and lock in the chosen design tokens.
- [ ] Both mockups pass WCAG AA contrast checks
- [ ] The user's choice is recorded in `docs/design.md` and `tokens.css`

Commit:

#### TASK-23: Frontend

**TASK-23.1:** Build the app shell, typed API client, state store, and match picker.
- [ ] The match list loads from the API with loading and error states

Commit:

**TASK-23.2:** Build the animated pitch canvas with playback controls (play, pause, speed, seek).
- [ ] Renders at 60 fps by interpolating 5 Hz frames, and seeking resumes the SSE stream correctly

Commit:

**TASK-23.3:** Build the overlays, moment timeline, momentum chart, and pitch-control heatmap toggle.
- [ ] At most 3 cues show at once (highest priority wins), and clicking a timeline marker seeks

Commit:

**TASK-23.4:** Build the Game/Team/Player tabs, insight cards with confidence labels, and the Ask why panel with the counterfactual arrow.
- [ ] Ask why shows the claims, cited events, and agent trace for an insight

Commit:

**TASK-23.5:** Add the persona bar, favorites, the 5-language i18n, and RTL support.
- [ ] Switching language or persona refetches insights, and Arabic sets `dir="rtl"`

Commit:

**TASK-23.6:** Pass accessibility and responsiveness checks and add the Playwright smoke test in CI.
- [ ] axe reports no serious violations; works at 375 px and fully by keyboard
- [ ] The Playwright smoke test (open match, play, insight appears, switch language, Ask why) passes in CI

Commit:

#### TASK-24: Azure deployment

**TASK-24.1:** Write `azure.yaml` and the Bicep modules (Container Apps, Static Web Apps, SQL, Storage, monitoring, budget).
- [ ] `az bicep build` and the deployment what-if succeed

Commit:

**TASK-24.2:** Add the Dockerfile and the deploy workflow through `azd pipeline config` (GitHub OIDC).
- [ ] A push to `main` deploys with no stored secrets

Commit:

**TASK-24.3:** Seed the cloud with the precomputed replays and verify the live deployment.
- [ ] The public URL plays a replay, `/api/health` returns ok, and App Insights shows agent spans

Commit:

#### TASK-25: Local run and docs

**TASK-25:** Add the Docker Compose local run, the architecture doc, and a README mapped to the hackathon requirements.
- [ ] A fresh clone runs with `docker compose up` and shows all 8 replays
- [ ] The README maps every §4.1 requirement to code paths and credits all open-source dependencies

Commit:

### Phase 2: Additions after the core is polished

Priority order: 26 → 27 → 33 → 28 → 32 → 29 → 30.

#### TASK-26: Scenario Designer

**TASK-26.1:** Build the Scenario Designer agent and the scenario job API with a realism gate.
- [ ] A prompt becomes a valid scenario that passes the realism gate and appears as a new analysed match
- [ ] Rate limits are enforced

Commit:

**TASK-26.2:** Build the "Make a match" UI with job progress.
- [ ] Submitting a prompt shows progress and opens the new match when it is ready

Commit:

#### TASK-27: Ingest agent

**TASK-27.1:** Build the replay streamer with fault injection and the deterministic anomaly detector.
- [ ] Gaps, duplicates, bad coordinates, and out-of-order time are each detected

Commit:

**TASK-27.2:** Build the Ingest agent's recovery decisions and the Chaos-mode UI banner.
- [ ] After `replay_window` recovery, stats are identical to the clean run
- [ ] The UI shows the recovery live

Commit:

#### TASK-28: Overlay Director

**TASK-28:** Build the Overlay Director agent and the published broadcast overlay JSON schema.
- [ ] At most 3 visible cues and the timing rules are enforced in code, with a deterministic fallback
- [ ] `overlays.json` validates against `docs/overlay-schema.json`

Commit:

#### TASK-29: Streaming mode

**TASK-29:** Add the optional streaming mode through Event Hubs and Azure Functions.
- [ ] An end-to-end run on the Event Hubs emulator writes events and triggers the analysis

Commit:

#### TASK-30: Voice commentary

**TASK-30:** Add optional voice commentary with Azure AI Speech.
- [ ] Live lines play in all 5 languages from the cache, muted by default

Commit:

#### TASK-32: kloppy export

**TASK-32:** Export MatchMind synthetic data to kloppy tracking and event datasets.
- [ ] A round trip through kloppy keeps the frame, player, and pass counts

Commit:

#### TASK-33: MatchMind as an MCP tool

**TASK-33:** Expose the analysis workflow as an MCP tool with `WorkflowMCPTool` and demo it from GitHub Copilot Agent Mode.
- [ ] An MCP client lists `matchmind.analyze_moment` and gets a verified text back

Commit:

### Phase 3: Submission

#### TASK-31: Submission package

**TASK-31.1:** Write the video script and a repeatable Playwright capture script for the footage.
- [ ] The script fits within 1:58, and the capture runs the same way every time

Commit:

**TASK-31.2:** Edit the demo video with royalty-free audio and upload it to an allowed platform.
- [ ] The video is under 2:00, has no third-party marks, and its public URL works

Commit:

**TASK-31.3:** Finish the README pitch and judge testing instructions, run the final checks, and submit.
- [ ] The repo is public, CI is green, and the test URL works in a private browser window
- [ ] Submitted before 2026-10-27, 11:59 pm PT

Commit:

## In Progress

## Done
