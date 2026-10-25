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
| `Event` (frozen) | `event_id` must be `"{match_id}-eNNNNN"` (validator); `period ∈ {1,2}`; `end_x/end_y/outcome/receiver_id/ball_speed_ms` nullable; engine extras go in `extras`: decisions (`chosen_score`, `best_score`, `best_option`), `restart`, `lofted` (level-3 passes), `arrival_t` (when a pass or clearance was controlled; level 3), `xg`, `blocked`, `parried`, `heavy_touch`, `offside`, `deflection`, `own_goal`, `mods`. `out` events carry `extras.restart` (throw_in, goal_kick, corner) |
| `PlayerPos` (frozen), `TrackingFrame` | `ball = (x, y, z)`; `players` list per frame |
| `Player` | `number` 1–99; `pace`, `skill`, `stamina` in [0, 1]; `position ∈ GK/DF/MF/FW` |
| `Club` | colors as hex strings; `formation` like `"4-3-3"` |
| `MatchMeta`, `MatchData` | `added_time_s = (period1, period2)` seconds |
| `Moment` | `kind` (7 literals), `level` game/team/player, `event_ids` |
| `Claim` | `ref` = event_id or `"metric:<name>@<t>"` |
| `Insight` | `confidence` high/medium/low; `source` agent/template; `prompt_version` |
| `PersonalizedText`, `Variant` | `Persona`, `Lang` literals; `club_id` for club_fan, `player_id` for player_focus |
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

## Tables
_None yet._ Planned: matches, events, metrics, moments, insights, personalized, overlay_cues, agent_runs, season_*.
