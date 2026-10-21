# Data Model

**Status:** planned (TASK-2). Once `schemas.py` exists, list each model with its file and line, its key fields, and any non-obvious rules. Don't copy whole class bodies.

## Units and conventions
- Pitch 105 × 68 m, origin bottom-left. Home team attacks left → right in period 1.
- Tracking at 10 Hz (the API streams 5 Hz; the frontend interpolates to 60 fps).
- `t` = seconds since kickoff of the current period; `period ∈ {1, 2}`; added time per period is in `MatchMeta.added_time_s`.
- IDs: `event_id = f"{match_id}-e{n:05d}"`; SSE id = `f"{period}:{t:.1f}:{seq}"`.
- Personas `analyst | casual | club_fan | player_focus`; languages `en | es | pt | fr | ar`.

## Models
_None yet._

## Tables
_None yet._ Planned: matches, events, metrics, moments, insights, personalized, overlay_cues, agent_runs, season_*.
