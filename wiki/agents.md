# Agents

**Status:** the MCP stats server is built (TASK-15); the agents are planned (TASK-16 to TASK-20; phase two: 26, 27, 28, 33).

| Agent | Module | Prompt | Output | Status |
|---|---|---|---|---|
| Tactical Analyst | `agents/analyst.py` | `prompts/analyst.v1.md` | `AnalystDecision` | planned |
| Explainer | `agents/explainer.py` | `prompts/explainer.v1.md` | `Insight` | planned |
| Verifier | `agents/verifier.py` | `prompts/verifier.v1.md` | `Verdict` | planned |
| Narrative | `agents/narrative.py` | `prompts/narrative.v1.md` | live line, `Recap` | planned |
| Personalization | `agents/personalizer.py` | `prompts/personalizer.v1.md` | `list[PersonalizedText]` | planned |
| Scenario Designer | `agents/scenario_designer.py` | | `Scenario` | phase 2 |
| Ingest | `agents/ingest.py` | | recovery action | phase 2 |
| Overlay Director | `agents/overlay_director.py` | | `list[OverlayCue]` | phase 2 |

## Runtime
- Client: Agent Framework `FoundryChatClient` + `DefaultAzureCredential`. Tests use `FakeChatClient`.
- MCP: stats tools at `/mcp` (see below).
- Retries: 1 s / 2 s / 4 s backoff; at most 2 Verifier-driven regenerations; then a template fallback.

## MCP stats server (`mcp_server/server.py`, TASK-15)
`build_mcp(repo, store) -> MCPServer` named `matchmind-stats`. The MCP Python SDK 2.x renamed FastMCP to `MCPServer`. `mcp_app()` is the streamable-HTTP ASGI app (Starlette) for `/mcp` (Task 21). The tools wrap `StatsService`, which can also be used directly.

| Tool | Returns (all with `ref`) |
|---|---|
| `get_match_summary(match_id)` | teams, stadium, kickoff, added time, score, goal refs, moment count (`match:<id>`) |
| `get_events(match_id, period, t_from, t_to, types)` | events in the window; each `ref` = event id |
| `get_team_metrics(match_id, team_id, period, t)` | every `TEAM_METRICS` value at t |
| `get_player_stats(match_id, player_id, period, t)` | every `PLAYER_METRICS` value at t (`on_pitch_yet`) |
| `get_metric(match_id, name, scope, scope_id, period, t)` | one value |
| `get_moment(moment_id)` | the moment, its details (deviation p-value and so on), and team metrics stored at its `t_end` |
| `get_counterfactual(event_id)` | chosen, best, gain, top 5 alternatives |
| `get_season_context(entity_id)` | club: position, table row, results, milestones; player: season totals, milestones, discipline |
| `get_player_profile`, `get_club_profile` | the profile (`profile:<id>`) |
| `get_player_baseline(player_id)` | per-90 baseline (`baseline:<id>`) |
| `get_player_deviations(match_id, period, t)` | flagged deviations at t (sprints skipped: no frames) |

- **Event-exact:** time-scoped tools compute `stats.metrics.snapshot` from events up to (period, t), plus the single frame territory needs, cached per (match_id, period, t) (LRU, 256). They never return the latest 30 s row, and never use anything after t. Metric refs are `metric:<name>@<period>:<t>`.
- **Errors:** unknown ids, teams, players, or metric names return `{"error": ...}`, not an exception.
- **Live, against the built database:** summary 80 ms; first team snapshot about 0.6 s (cached after); deviations 130 ms; season context 1 ms.

## Number checking (`agents/numbers.py`, TASK-16.2)
The Verifier's deterministic rule: every number an agent writes must match a verified stat, a real event minute, the real score, or a formation actually used. Nothing is skipped.

- `extract_numbers(text, lang) -> list[ExtractedNumber]` reads numbers the way each language writes them:
  - decimal commas (`es`, `pt`, `fr`: "1,5");
  - thousands separators ("12.000", "12 000" including narrow spaces, "12,000");
  - Arabic-Indic digits with Arabic separators ("١٢٬٠٠٠", "٣٫٥");
  - number words 0–20 in all 5 languages, including Arabic teens ("ثلاثة عشر") and prefixes ("و", "ال").
- **Units:** `%` (and "por ciento", "pour cent"), `km/h`, `m/s`, `km`, `m`.
- **Minute marks:** "62'", "62nd minute", "minuto 62", "62e minute", "الدقيقة ٦٢", and "90+3'" (read as 93).
- **Scorelines** ("2-1", "2 a 1") and **formations** ("4-2-3-1") are read as one token each.
- A separator that isn't a 3-digit group is read as a decimal point in any language ("1.5" in Spanish is 1.5).
- Words for 1 (un, una, um, une, one, واحد) are not numbers: they double as articles.
- `check_text(text, lang, claims, lookup, rel_tol=0.01, abs_tol=0.05, *, minutes, scores, formations) -> NumberCheck(ok, failures)`:
  - Each claim must agree with its stored value, compared at the claim's own precision.
  - Each number in the text must match a verified claim. Unit conversion is allowed (km/h ↔ m/s, m ↔ km, ratio ↔ %), and so is rounding to the written precision ("12" for 11.6, but not "12.0").
  - Minutes, scores (either order) and formations must be in the sets passed in.

## Gotchas
- **MCP SDK 2.x:** `mcp.server.fastmcp` no longer exists (`MCPServer` is in `mcp.server.mcpserver`). A raised exception comes back as a generic "Error executing tool", so tools return an `error` dict instead. Tests connect in-process with `mcp.Client(server)`.
_Add any surprises from the Agent Framework or Foundry APIs here._
