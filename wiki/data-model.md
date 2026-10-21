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
| `Event` (frozen) | `event_id` must be `"{match_id}-eNNNNN"` (validator); `period ∈ {1,2}`; `end_x/end_y/outcome/receiver_id/ball_speed_ms` nullable; engine extras (`chosen_score`, `best_score`, `best_option`) go in `extras` |
| `PlayerPos` (frozen), `TrackingFrame` | `ball = (x, y, z)`; `players` list per frame |
| `Player` | `number` 1–99; `pace`, `skill`, `stamina` in [0, 1]; `position ∈ GK/DF/MF/FW` |
| `Club` | colors as hex strings; `formation` like `"4-3-3"` |
| `MatchMeta`, `MatchData` | `added_time_s = (period1, period2)` seconds |
| `Moment` | `kind` (7 literals), `level` game/team/player, `event_ids` |
| `Claim` | `ref` = event_id or `"metric:<name>@<t>"` |
| `Insight` | `confidence` high/medium/low; `source` agent/template; `prompt_version` |
| `PersonalizedText`, `Variant` | `Persona`, `Lang` literals; `club_id` for club_fan, `player_id` for player_focus |
| `OverlayCue` | `kind` (7 literals), `t_in`/`t_out`, `priority`, free `payload` |

Type aliases: `EventType`, `Period`, `Persona`, `Lang`, `Level`, `MomentKind`, `CueKind`.

## Geometry (`engine/pitch.py`)
`PITCH_LENGTH = 105.0`, `PITCH_WIDTH = 68.0`; `clamp_to_pitch(x, y)`; `zone_index(x, y, nx=16, ny=12) -> (col, row)`, with edge and out-of-bounds points clamped into the grid; `distance(a, b)`.

## Tables
_None yet._ Planned: matches, events, metrics, moments, insights, personalized, overlay_cues, agent_runs, season_*.
