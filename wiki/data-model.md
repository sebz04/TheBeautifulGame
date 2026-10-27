# Data Model

**Status:** models done (TASK-2) in `src/matchmind/schemas.py`; DB tables planned (TASK-14). Geometry in `src/matchmind/engine/pitch.py`.

## Units and conventions
- Pitch 105 × 68 m, origin bottom-left. Home team attacks left → right in period 1.
- Tracking at 10 Hz (the API streams 5 Hz; the frontend interpolates to 60 fps).
- `t` = seconds since kickoff of the current period; `period ∈ {1, 2}`; added time per period is in `MatchMeta.added_time_s`.
- IDs: `event_id = f"{match_id}-e{n:05d}"`; SSE id = `f"{period}:{t:.1f}:{seq}"`.
- Personas `analyst | casual | club_fan | player_focus`; languages `en | es | pt | fr | ar`.

## Models (`schemas.py`)
| Model | Key fields / rules |
|---|---|
| `Event` (frozen) | `event_id` must be `"{match_id}-eNNNNN"` (validator); `period ∈ {1,2}`; `end_x/end_y/outcome/receiver_id/ball_speed_ms` nullable; engine extras go in `extras`: decisions (`chosen_score`, `best_score`, `chosen_option`, `best_option`, `risk_weight`, `goal_window`), `restart`, `lofted` (level-3 passes), `arrival_t` (when a pass or clearance was controlled; level 3), `xg`, `blocked`, `parried`, `heavy_touch`, `offside`, `deflection`, `own_goal`, `mods`. `out` events carry `extras.restart` (throw_in, goal_kick, corner) |
| `PlayerPos` (frozen), `TrackingFrame` | `ball = (x, y, z)`; `players` list per frame |
| `Player` | `number` 1–99; `pace`, `skill`, `stamina` in [0, 1]; `position ∈ GK/DF/MF/FW` |
| `Club` | colors as hex strings; `formation` like `"4-3-3"` |
| `MatchMeta`, `MatchData` | `added_time_s = (period1, period2)` seconds |
| `Moment` | `kind` (10 literals: momentum_swing, pressing_collapse, formation_shift, big_chance, goal, red_card, sprint_alert, offside_trap, corner_pressure, player_deviation), `level` game/team/player, `event_ids` |
| `Claim` | `ref` = event_id, `"metric:<name>@<period>:<t>/<team|player>:<id>"`, or `"deviation:<stat>@<period>:<t>/player:<id>"`; counterfactual claims use metric `counterfactual_*` and an event id ref |
| `Verdict` | `ok`, `failures` (actionable sentences; `qualitative: …` from the agent), `fixed_claims` (claims with the stored value) |
| `AgentRun` | one agent call or fallback: `agent` (`template:<step>` for fallbacks), `status` ok/retry/failed/fallback, `attempts`, `latency_ms`, `trace_id`, `error`, `tokens_in`, `tokens_out` |
| `Recap` | `title`, `paragraphs`, `key_numbers` (the verified claims it cites), `verified`, `source` agent/template |
| `AnalystDecision` | `moment_id`, `surface`, `level`, `priority` 1–5, `tactical_context` (no numbers), `metrics_to_cite` |
| `Insight` | `confidence` high/medium/low; `source` agent/template; `prompt_version` |
| `PersonalizedText`, `Variant` | `Persona`, `Lang` literals; `club_id` for club_fan, `player_id` for player_focus; `dir` ("rtl" for Arabic); `source` agent/template |
| `OverlayCue` | `kind` (7 literals), `t_in`/`t_out`, `priority`, free `payload` |

`trusted(cls, data)` builds a model without validation, about 3× cheaper than `model_construct`. Use it only for data our own code produced (engine frames, our Parquet files).

Type aliases: `EventType`, `Period`, `Persona`, `Lang`, `Level`, `MomentKind`, `CueKind`.

`EventType`: kickoff, pass, carry, shot, tackle, interception, pressure, foul, card, sub, goal, out, save, clearance, offside. An `offside` event is credited to the attacking team and the flagged player, with `extras.timing_error_s` and the runner's active mods (TASK-9.2).

## Geometry (`engine/pitch.py`)
`PITCH_LENGTH = 105.0`, `PITCH_WIDTH = 68.0`; `attacks_right(is_home, period)` (home attacks right in period 1); `clamp_to_pitch(x, y)`; `zone_index(x, y, nx=16, ny=12) -> (col, row)`, with edge and out-of-bounds points clamped into the grid; `distance(a, b)`.

## Match files (`engine/match_io.py`)
`write_match(data, out_dir)` / `read_match(out_dir) -> MatchData`. One directory per match:
- `meta.json`: `MatchMeta`, sorted keys.
- `events.parquet`: one row per `Event`; `extras` stored as a JSON string.
- `frames.parquet`: **long format**, one row per player per frame (`frame, period, t, ball_x, ball_y, ball_z, player_id, team_id, x, y, vx, vy`), rows grouped by frame. This is the shape pandas or numpy readers want.
Zstd compression, no embedded schema metadata: the same data gives byte-identical files. Reading builds frames with `schemas.trusted` (no validation; they come from our own writer) with the GC paused, and fully validates events. One match: frames about 7.4 MB, events about 40 KB; write about 1 s, read about 3 s.

## Tables (`store/db.py`, TASK-14.1)
SQLAlchemy Core with portable types only (JSON stored as text), so the same schema runs on SQLite (`MATCHMIND_DB_URL`, default `sqlite:///data/matchmind.db`) and Azure SQL (`pyodbc`, `azure` extra). `make_engine(url)`: an `mssql+…` URL signs in with an Entra ID token added to every new connection (`DefaultAzureCredential`, scope `https://database.windows.net/.default`), with pooled connections recycled every 30 min and `fast_executemany` for bulk loads.
- `matches` (meta JSON); `events` (columns + `extras_json`).
- `metrics` (`match_id, period, t, scope, scope_id, name, value, kind`), indexed for latest-before-t lookups.
- `moments` (+ `event_ids_json`, `details_json` for a deviation's expected, baseline per 90, and p-value).
- `insights`, `personalized` (persona, lang, club_id, player_id), `overlay_cues`, `agent_runs` (with `tokens_in`, `tokens_out`).
- `narratives` (`key`, `match_id`, `kind`, `body_json`): live lines (`line:<insight>`), the recap (`recap:<match>`), moments the Analyst passed on (`passed:<moment>`), and the realism report (`realism:<match>`, written by `matchmind build`, kept by `clear_agent_outputs`).
- `season_results`, `season_standings`, `season_player_lines`, `season_meta` (rounds, milestones, discipline, sat-out lists).

`Repo(url)`:
- **Matches:** `save_match_data` (meta and events; replaces), `get_match_meta`, `list_matches`, `get_events(match_id, t_from, t_to, types)`.
- **Metrics:** `save_metrics` (replaces the match's rows), `list_metrics`, `get_metric(match_id, name, scope, scope_id, (period, t))`, which returns the latest value at or before t, or None.
- **Moments:** `save_moments(match_id, moments, details)`, `list_moments` (time order), `moment_details`.
- **Insights:** `save_insight` (upsert), `list_insights(match_id)`, `save_personalized`, `list_personalized(match_id, persona, lang)`.
- **Cues and agent runs:** `save_cues`, `list_cues`, `log_agent_run`, `list_agent_runs(moment_id)`, `list_match_runs(match_id)`.
- **Narratives:** `save_live_line`, `list_live_lines`, `save_recap`, `get_recap`, `save_passed_moments`, `list_passed_moments`, `save_realism`, `get_realism`; `clear_agent_outputs(match_id)` deletes every agent output of a match (precompute `--reset`).
- **Season:** `save_season`, `load_season`.
- **Rebuilds:** `delete_match`.

`MetricRow` and `AgentRun` are shared models in `schemas.py`.

## Tracking store (`store/blob.py`, TASK-14.2)
- `TrackingStore(backend)`: `write(match_id, frames)` replaces the match's frames; `read_window(match_id, period, t_from, t_to)` returns exactly the frames of that period with t_from ≤ t ≤ t_to (empty if t_from > t_to); `read_all`, `exists`. A missing match raises `LookupError`.
- Format: the match-file Parquet layout (`match_io.frames_table` / `frames_from_table`), zstd, in one-minute row groups, so a window read decodes only what it touches.
- `tracking_store(settings)`:
  - local `<data_dir>/tracking/<match_id>/frames.parquet`, written atomically (`LocalBackend`);
  - or, when `MATCHMIND_BLOB_ACCOUNT_URL` is set, the Azure Blob container `tracking` (`AzureBackend`, with `DefaultAzureCredential` and no keys; needs the `azure` extra).
