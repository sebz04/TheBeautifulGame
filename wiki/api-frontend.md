# API and Frontend

**Status:** API read endpoints built (TASK-21.1); live SSE (21.2) and regenerate, `/mcp`, CORS (21.3) next. Frontend planned (TASK-22 to TASK-23). The full contract is in plan Task 21.

## API (`src/matchmind/api/`)
- **Run:** `uv run uvicorn matchmind.api.app:app` (port 8000). The served app warms its caches (realism, momentum) in a background thread at startup; the first match detail is otherwise about 10 s.
- **`create_app(repo=None, store=None, *, warm=False)`** builds the app; tests pass an in-memory `Repo` and a temp `TrackingStore`.
- **`Services`** (`services.py`, on `app.state.services`, injected as `Svc`): the repo, the tracking store, the MCP `StatsService` (metrics, profiles, baselines, counterfactuals), and per-match caches of events, realism, and momentum.
- **Errors:** unknown match, insight, team, or player → 404; invalid query values (persona, lang, scope, period not 1–2, a tracking window over 60 s) → 422.

## Endpoints
| Route | File | Returns |
|---|---|---|
| `GET /api/health` | `routes_matches.py` | `{ok, version}` |
| `GET /api/matches` | `routes_matches.py` | `[{match_id, title, home, away, score, scenario_id}]` |
| `GET /api/matches/{id}` | `routes_matches.py` | `MatchMeta` + `score` + `realism` (`RealismReport`) |
| `GET /api/matches/{id}/tracking?period=&from=&to=` | `routes_matches.py` | `{frames}` at 10 Hz, at most 60 s |
| `GET /api/matches/{id}/timeline` | `routes_matches.py` | `{moments, momentum: [{period, t, home, away, diff}]}` |
| `GET /api/matches/{id}/insights?persona=&lang=&club_id=&player_id=` | `routes_insights.py` | `[{insight, text}]` in time order |
| `GET /api/insights/{id}/why` | `routes_insights.py` | `{claims, events, agent_runs, trace_id, counterfactual}` |
| `GET /api/matches/{id}/stats?scope=&scope_id=&period=&t=` | `routes_matches.py` | `{metrics, baseline, profile}` |
| `GET /api/matches/{id}/pitch-control?period=&t=` | `routes_matches.py` | `{grid: 21 × 32, attacking_team}` |
| `GET /api/matches/{id}/recap?lang=&persona=` | `routes_matches.py` | `Recap` |
| `GET /api/league` | `routes_matches.py` | `{clubs, players}` |

- **Insights:** `club_fan` texts are for `club_id` (default: the home club); `player_focus` needs a `player_id` in the match. A variant the precompute didn't write (another club's fan, a player no claim is about) gets its template from `templates.render`, so every insight has a text.
- **Why:** the counterfactual is for the first cited decision event (pass, carry, shot, clearance), else `null`. `trace_id` is `null` for the TASK-20.2 precompute (tracing was off then).
- **Stats:** `baseline` is the player's season expectation so far (`stats.deviations.expected_so_far`: per-90 rates × minutes played, adjusted for possession and red cards); `null` for teams or players without a season line.
- **Pitch control:** the last frame at or before t (within 0.5 s); the attacking team is the team of the last event.
- **Recap:** English only for now; `lang` and `persona` are validated, then ignored (translation is in TASK-25.2).

## SSE contract
Event types `frame | event | cue | insight | end`. `id = "{period}:{t:.1f}:{seq}"`. Resuming with `Last-Event-ID` or `from_t` must give no duplicates.

## Frontend
_Design direction: not chosen yet (TASK-22)._ Components are listed here as they land, with their path and what they consume.
