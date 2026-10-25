# Orchestrator

**Status:** built (TASK-20.1 workflow, retries, logging; TASK-20.2 precompute). The agents it runs are on [agents.md](agents.md), [verifier.md](verifier.md), and [personalization.md](personalization.md).

## The workflow (`agents/orchestrator.py`)
An Agent Framework graph (`WorkflowBuilder`, `@executor` steps), run once per 5-minute window of a match:

`analyst` → `explainer_verifier` → `narrative` → `personalizer_verifier`

- **`analyst`:** `analyze` on the window's moments that have no insight yet.
- **`explainer_verifier`:** `verify_loop` per surfaced moment (Explainer ⟲ Verifier, at most 2 regenerations). If no explanation is verified, or the model fails, the moment gets **`template_insight`**: a headline by moment kind, the minute, no numbers, `source="template"`. Every surfaced moment still gets a card.
- **`narrative`:** a live line per insight. Template insights, or a failed call, use the headline.
- **`personalizer_verifier`:** `personalize_batch` per (insight, language), then **one Verifier call for all of that language's agent-written texts** (`verify_texts`). The Verifier's failures are mapped back to texts by their quoted statement; those texts, or all of them if it's unclear, get their templates. Template insights get templates in every language.
- **API:**
  - `run_window(match_id, period, t_from, t_to, deps) -> WindowReport` covers moments starting in `[t_from, t_to)`.
  - `run_match(match_id, deps, *, max_windows=2, limit=None) -> PipelineReport` runs every window, then the full-time recap (agent or template). `limit` runs only the first windows and skips the recap.
- **`Deps`:** `repo`, `client`, `tools`, `facts_for(match_id)`, `sleep` (the backoff clock), `langs`, `limiter`, and `max_parallel` (moments at once).
- **Saving:** each step saves as it goes (insights, live lines, texts, recap), and the window's agent runs are logged at its end.
- **Resumable:** a moment that already has an insight, a live line, and texts in every language is skipped (`WindowReport.skipped`). A partly done moment continues where it stopped.
- **Copying:** the workflow deep-copies messages between steps. The shared window state (`_Window`: store, facts with the DB engine, run log) returns itself from `__deepcopy__`. No checkpoints are used.

## Retries, logging, throttling (`agents/runtime.py`)
- **Retries:** `run_agent` retries **transient errors** after 1 s, 2 s, and 4 s pauses, then raises, and the step falls back to a template.
  - Transient (`is_transient`) means 429, timeouts, connection errors, and 5xx, found by exception type, status code, or message.
  - A malformed reply is not transient: the agents' own one regeneration handles it.
- **`pipeline_scope(log=, sleep=, limiter=)`** (a context variable) applies to every `run_agent` inside it:
  - each call becomes an **`AgentRun`** row: agent, moment, status `ok`, `retry`, or `failed`, attempts, latency, trace id, error, `tokens_in`, and `tokens_out`;
  - fallbacks add `template:<step>` rows with status `fallback` and the reason.
- **`TokenBucket(tpm)`** throttles to the quota. It acquires an estimate before each call and settles with the real usage after.
- `FakeChatClient` reports estimated token usage (4 characters a token), so tests see token counts too.

## Lessons from the live smoke (1 window, 2 insights)
- **The Explainer cited 126–131 events** (every event of the window it fetched). That made every Verifier call 46k tokens, with a p95 latency of 58 s.
  - Insights now keep **at most 8 key events** (`explainer.MAX_EVENTS`): the moment's own first, then those the claims cite.
  - `get_events` returns the latest **40** events without the engine's decision scoring (`mcp_server.MAX_EVENTS`).
  - Result: one window went from 3.8 to 1.1 min, and p95 from 58 s to 8 s.
- **Minute ranges** ("entre el minuto 5 y 13") are now read as minutes: a number joined to a minute by and, y, e, et, و, to, or a dash, going forward in time.
- **A window length ("the last 10 minutes")** matches only exactly, as a whole number: "9.9" passed briefly as "10".
