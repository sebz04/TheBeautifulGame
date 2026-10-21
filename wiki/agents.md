# Agents

**Status:** planned (TASK-15 to TASK-20; phase two: 26, 27, 28, 33).

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
- MCP: stats tools at `/mcp`.
- Retries: 1 s / 2 s / 4 s backoff; at most 2 Verifier-driven regenerations; then a template fallback.

## Gotchas
_Add any surprises from the Agent Framework or Foundry APIs here._
