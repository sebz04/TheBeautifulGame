# Agents

**Status:** the MCP stats server (TASK-15), number checking and the runtime (TASK-16), and the Tactical Analyst and Explainer (TASK-17) are built. The Verifier, Narrative, Personalizer, and workflow are planned (TASK-18 to TASK-20; phase two: 26, 27, 28, 33).

| Agent | Module | Prompt | Output | Status |
|---|---|---|---|---|
| Tactical Analyst | `agents/analyst.py` | `prompts/analyst.v1.md` | `AnalystDecision` | done (17.1) |
| Explainer | `agents/explainer.py` | `prompts/explainer.v1.md` | `Insight` | done (17.2) |
| Verifier | `agents/verifier.py` | `prompts/verifier.v1.md` | `Verdict` | planned |
| Narrative | `agents/narrative.py` | `prompts/narrative.v1.md` | live line, `Recap` | planned |
| Personalization | `agents/personalizer.py` | `prompts/personalizer.v1.md` | `list[PersonalizedText]` | planned |
| Scenario Designer | `agents/scenario_designer.py` | | `Scenario` | phase 2 |
| Ingest | `agents/ingest.py` | | recovery action | phase 2 |
| Overlay Director | `agents/overlay_director.py` | | `list[OverlayCue]` | phase 2 |

## Runtime (`agents/runtime.py`, TASK-16.3)
Agent Framework 1.23 (`agent-framework-core`, `agent-framework-foundry`).
- `make_chat_client(settings, credential=None)`: a `FoundryChatClient` for `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL_DEPLOYMENT`, signed in keylessly with `DefaultAzureCredential`. It raises if the endpoint isn't set.
- `make_agent(name, prompt_file, output_model, tools, *, client) -> Agent`:
  - instructions are read from `agents/prompts/<prompt_file>`, or from the path if it is absolute;
  - `response.value` is the reply parsed into `output_model` (`response_format`).
- `run_agent(agent, message, *, moment_id, attempt, tracer=None)`:
  - runs the agent once inside a span `agent_run <name>` with `matchmind.agent`, `matchmind.moment_id` and `matchmind.attempt`;
  - errors mark the span and are re-raised for the retry policy.
- `FakeChatClient(responses)`: for tests.
  - `responses` is a mapping from a substring (looked for in the instructions and messages; `"*"` is the fallback) to a reply, or a callable `(FakeCall) -> str`.
  - Every request is kept in `.calls`.
  - A missing reply raises `KeyError`.
- `stats_tools(settings, *, session=None)`: an `MCPStreamableHTTPTool` for the 12 stats tools at `MATCHMIND_MCP_URL`, or an open in-process MCP session.
- `configure_tracing(settings) -> bool`: Application Insights through `AzureMonitorTraceExporter` and Agent Framework's `configure_otel_providers`. With no connection string, or an invalid one, tracing is off and a warning is logged.
- `python -m matchmind.agents.runtime --ping`: a live smoke test.
- Retries (TASK-20): 1 s / 2 s / 4 s backoff; at most 2 Verifier-driven regenerations; then a template fallback.

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

## Tactical Analyst (`agents/analyst.py`, TASK-17.1)
- `batches(moments, minutes=5)` groups moments into 5-match-minute windows per period. `analyze(batch, client, tools) -> list[AnalystDecision]` returns only surfaced moments, highest `priority` first.
- `AnalystDecision(moment_id, surface, level, priority 1–5, tactical_context, metrics_to_cite)` is in `schemas.py`. `tactical_context` has no numbers.
- **Every surfaced moment must be looked up.** A tool call counts if it names the `moment_id` or one of its events, or is time-scoped (`t`, or `t_from`/`t_to`) to the moment's period within 60 s of its window.
  - If a moment isn't looked up, the batch is sent once more, naming the moments that were skipped (attempt 2).
  - Anything still not looked up is dropped.
- Decisions for moment ids not in the batch are ignored. The first decision per moment wins.
- The prompt states Constitution I and II verbatim, with 2 worked examples. Metric names in it are the real `TEAM_METRICS`, `PLAYER_METRICS`, and `TRACKED_STATS` names.
- Tests: `tests/agents/conftest.py` has `StatsStub`, Agent Framework `@tool` stand-ins with the MCP tool names that record their calls. `FakeChatClient` replies can be `[tool_call(name, **args)]`, and a callable reply sees earlier results in `call.tool_results`.

## Explainer (`agents/explainer.py`, TASK-17.2)
- `explain(decision, moment, client, tools, *, names=None, tracer=None) -> Insight` returns an `Insight` with:
  - `insight_id` `<moment_id>-ins`, `source="agent"`, `verified=False`, `prompt_version="explainer.v1"`;
  - `trace_id` from the run's span (None when tracing is off).
- **Two models.** `ExplainerReply` is the plain `response_format`. `ExplainerDraft` adds the checks:
  - event ids and claims are present, and every claim has a ref;
  - headline, why, and recommendation aren't empty.
  - A failed check would fail the call inside the Foundry client (see Gotchas), which is why the reply model stays plain.
- **Counterfactual claims** (metric `counterfactual_*`) must cite an event id that `get_counterfactual` was called with in the same run.
- **One regeneration.** A bad reply (malformed JSON, a failed check, an unread counterfactual) is sent back once with the problem. A second bad reply raises `ExplainerError`, and TASK-20 falls back to a template. Service errors (timeouts, 429s) are raised as they are.
- The recommendation answers "What should they do?" (team and player) or "What to watch next" (game).

## Agent context (`agents/context.py`, `clock.py`)
- Agents are given `names` (club and player id → name, from `match_names(meta)`) and minute labels for each moment (`moment_context`: `minute_start` and `minute_end`, such as `56'`). Code computes both (Constitution I).
- `clock.minute_label(period, t)` follows football convention: 55:38 elapsed is `56'`, and stoppage time is `45+2'` or `90+3'`. `match_minute` gives the same as one number (45+2' → 47), the way the number checker reads it.

## Recorded fixtures (`tests/fixtures/llm/`)
- `scripts/record_llm_fixtures.py [--scenario comeback_red_card]` runs the real Analyst and Explainer on 3 moments (red card, goal, pressing collapse) against the built database. It uses the in-process stats server, and chat middleware records every reply.
- `tests/agents/test_recorded.py` replays the recordings through `FakeChatClient`. Live run on 2026-10-25: 8–15 s per moment.
- **What the first live run showed (fixed in prompt v1):**
  - ids used as names ("Ala-17");
  - clock times ("10:38") instead of minutes;
  - derived numbers (46.2% from 53.8%);
  - numbers without claims;
  - xG called "expected threat".
- **Still flagged after the fix:** "ten men". The number checker catches it, and the Verifier's regeneration (TASK-18) handles it.

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
- **Instructions travel in options, not messages:** a chat client sees `options["instructions"]`, and the messages are only the user turns. `FakeChatClient` searches both.
- **In-process MCP for tests:** pass `session=mcp.Client(server).session` (inside `async with`). Passing `mcp_client=` needs `tenacity` (not installed), and `url` and `mcp_client` can't be combined.
- **Close the async credential** (`async with DefaultAzureCredential()`), or aiohttp warns "Unclosed client session".
- **Structured replies are parsed inside the client.** `FoundryChatClient` (OpenAI `responses.parse`) validates the reply against `response_format` during the request, so a pydantic validator that fails turns into `ChatClientException` from `agent.run`, not an error on `.value`.
  - Keep `response_format` models plain and check afterwards.
  - `runtime.bad_reply(exc)` tells a malformed reply (a `ValidationError` inside) from a service error.
  - `FakeChatClient` parses the same way, so tests see what production sees.
- **Tool arguments arrive as a JSON string** from the real model (`runtime.tool_calls` decodes them). The fake sends a dict.
- **`get_metric` has an argument called `name`**, so `tool_call(tool_name, /, **args)` takes the tool name positionally.
- **Application Insights wants the connection string**, not the instrumentation key. A bare key raises `ValueError: Invalid connection string`, which `configure_tracing` turns into a warning.
_Add any surprises from the Agent Framework or Foundry APIs here._
