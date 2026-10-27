# API and Frontend

**Status:** API built (TASK-21): read endpoints, SSE live replay, live regenerate with rate limits, `/mcp`, CORS. Frontend planned (TASK-22 to TASK-23). Frontend planned (TASK-22 to TASK-23). The full contract is in plan Task 21.

## API (`src/matchmind/api/`)
- **Run:** `uv run uvicorn matchmind.api.app:app` (port 8000). The served app warms the cheap caches (momentum, replay index) in a background thread at startup.
- **Realism** is stored by `matchmind build` (`Repo.save_realism`); a match built before that is checked once on first request (about 10 s) and saved. It is not warmed: computing it holds the GIL for seconds and stalled live streams.
- **`create_app(repo=None, store=None, *, warm=False, settings=None, limiter=None, regenerator=None)`** builds the app; tests pass an in-memory `Repo`, a temp `TrackingStore`, a fake-clock `RateLimiter`, and a fake regenerator.
- **CORS:** only `MATCHMIND_WEB_ORIGIN` (the Static Web App) and `localhost:5173`, methods GET and POST.
- **`/mcp`:** the MCP stats server (streamable HTTP), mounted last at the root so it only sees `/mcp`; its session manager runs in the app lifespan. The SDK's DNS-rebinding check allows localhost plus `MATCHMIND_API_HOST` (set it to the deployed host name).
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
| `POST /api/matches/{id}/regenerate` | `routes_insights.py` | `{insight, text, agent_runs, trace_id}` |

- **Insights:** `club_fan` texts are for `club_id` (default: the home club); `player_focus` needs a `player_id` in the match. A variant the precompute didn't write (another club's fan, a player no claim is about) gets its template from `templates.render`, so every insight has a text.
- **Why:** the counterfactual is for the first cited decision event (pass, carry, shot, clearance), else `null`. `trace_id` is `null` for the TASK-20.2 precompute (tracing was off then).
- **Stats:** `baseline` is the player's season expectation so far (`stats.deviations.expected_so_far`: per-90 rates × minutes played, adjusted for possession and red cards); `null` for teams or players without a season line.
- **Pitch control:** the last frame at or before t (within 0.5 s); the attacking team is the team of the last event.
- **Recap:** English only for now; `lang` and `persona` are validated, then ignored (translation is in TASK-25.2).

## Regenerate (live agent run)
- Body `{moment_id, persona, lang, club_id?, player_id?}`. Runs `orchestrator.regenerate`: Explainer ⟲ Verifier on the moment (the Analyst is skipped: the moment is already chosen), then one Personalizer text checked by the Verifier in `lang`, with the usual template fallbacks. **Nothing is saved**: the precomputed replay stays as reviewed.
- **Limits** (`ratelimit.py`, in memory): 5 an hour per visitor, 100 a day in all; over either, 429 `{detail, retry_after}` plus a `Retry-After` header. Invalid requests (404, 422) are not counted. The visitor is the rightmost `X-Forwarded-For` entry (the ingress's), else the socket peer.
- 120 s timeout (504). Live check: 26 s, about 57k tokens ($0.03), with a trace id.

## Live replay (`routes_live.py`)
`GET /api/matches/{id}/live?period=1&from_t=0&speed=1` → SSE (`sse-starlette`, ping every 15 s).
- **Messages:** `frame` (5 Hz of the 10 Hz tracking: `{frame, period, t, ball, players: [{player_id, team_id, x, y}]}`), `event` (without decision scoring), `cue` (`OverlayCue`, at `t_in`), `insight` (at its moment's end: `{insight_id, moment_id, level, headline, source, live_line}`; localized texts come from the insights endpoint), then `end`.
- **Ids:** `"{period}:{t:.1f}:{seq}"`. `seq` is the message's place in one fixed ordering of the whole match (by period, t, then frame, event, cue, insight), so it is the same on every connection.
- **Resume and seek:** `Last-Event-ID` continues at `seq + 1`; `from_t` starts at the first message at or after `(period, from_t)`. Seeking backwards is a new request.
- **Pacing:** on the match clock at `speed` (0 to 32; 0 = no pacing). Cues are the fast lane: precomputed, sent at `t_in`, independent of the agents (tested: within 1 s at speed 1).
- **Index:** `build_index` lists every message's time once per match (cached; frame times from 3 Parquet columns via `TrackingStore.frame_times`). Frame bodies are read from the store 20 s at a time while streaming.

## Frontend (`web/`)
Design: `docs/superpowers/specs/2026-10-26-frontend-visual-direction-design.md`; plan: `docs/superpowers/plans/2026-10-26-frontend.md`. Direction: **broadcast-dark** (`docs/design.md`): near-black square panels on the club field, *Big Shoulders Display* + *Schibsted Grotesk*, a night pitch; the view is set by two switches (Team ⇄ Player, Fan ⇄ Scout) and a language menu. Mockups: `web/mockups/` (`node web/scripts/contrast.mjs web/mockups/*.html` checks their contrast).
- **Stack:** React 18.3, Vite 5, TypeScript 5.6, Tailwind 3.4; Vitest + Testing Library (jsdom). Versions pinned exactly in `web/package.json`.
- **Commands** (in `web/`): `npm run dev` (port 5173; proxies `/api` and `/mcp` to `localhost:8000`), `npm test`, `npm run lint` (type check), `npm run build`.
- **Tokens** (`src/design/tokens.css`): `--mm-bg` (page field), `--mm-text-on-bg`, `--mm-surface` (cards), `--mm-text`, `--mm-muted`, `--mm-accent`, `--mm-on-accent`, `--mm-home`, `--mm-away`, `--mm-good`, `--mm-warn`, fonts, `--mm-space-1..8`. Tailwind maps them to colors (`bg-bg`, `text-accent`, …).
- **Routes** (`src/App.tsx`, react-router 6): `/matches` (`MatchPicker`: the fan's club's matches first, loading and error states with retry), `/match/:id` (`Match`: layout B shell, score bar, "About this match" → `RealismPanel` with plain check names). `/` redirects to `/matches` until the welcome page (TASK-23.7).
- **API client** (`src/api/client.ts`, types in `src/api/types.ts` mirroring the API): `api.matches()`, `match`, `tracking`, `timeline`, `insights`, `why`, `stats`, `pitchControl`, `recap`, `league`, `regenerate`; non-2xx throws `ApiError {status, detail, retry_after?}`.
- **State** (`src/state/`): `prefs.ts` (`{mode, focus, lang, favorite_club_id, favorite_player_id, sides}` in `localStorage` under `matchmind.prefs`; every access guarded, invalid values fall back to `DEFAULT_PREFS`), `store.ts` (Zustand: prefs plus playback `period`, `t`, `playing`, `speed`). `useAsync` (`src/lib/`) gives loading, error, and retry.
- **Live replay** (`src/live/`, driven from the store so it survives a tab switch): `openLive(matchId, {period, from_t, speed}, handlers, seenInsights)` wraps `EventSource` (the browser reconnects with `Last-Event-ID`); it drops messages at or below the stream's last seq and delivers each insight once per session. Store actions `openMatch`, `play`, `pause`, `seek(period, t)`, `setSpeed` (reopen at the current time). `interpolate`, `clockOf`/`fromClock` (one clock across half time), `minuteLabel` ("45+2'"), `scoreAt` (score at t from the timeline's goal moments).
- **Pitch** (`components/Pitch.tsx`): canvas redrawn every animation frame, 200 ms behind the newest 5 Hz frame, interpolated (measured 61 fps); `dir="ltr"` always; y = 0 is the bottom touchline. **PlaybackBar**: play/pause (Space), speeds 0.5–8×, a match-time slider across both halves.
- **Match flow** (TASK-23.3): `Overlays` (cues active at t, at most 3, highest priority then newest; name tags and speed alerts pinned to the player, distance alerts in a corner), `Timeline` (one marker per moment with a plain name such as "Player stands out, 61'"; click or Enter seeks), `MomentumChart` (visx areas of home − away, playhead), `StatsStrip` (xG, possession, shots, on target, PPDA for both teams at t, every 5 s), and the pitch-control heatmap toggle (fetched at most once a second, drawn smoothly under the players in the attacking team's color). While paused, a seek fetches the still frame at that time.
- **Club takeover** (`src/design/theme.ts`): `clubTheme(club, surface)` keeps the club's primary exactly as the page field, puts near-black or white text on it, and nudges the secondary's lightness until text on it passes. `applyTheme` sets the variables on `<html>`. Tested: all 20 clubs on both surfaces pass AA (4.5:1) for text on page, on cards, and on the accent; so does `NEUTRAL_THEME`.
