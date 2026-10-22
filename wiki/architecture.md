# Architecture

**Status:** designed, not built. Update the Status column as components land.

## Flow
```
Scenario (YAML or Scenario Designer)
  → Engine (seeded, event-coupled) ── events → Azure SQL / SQLite
                                   └─ 10 Hz tracking → Blob / local Parquet
  → Stats engine (xT, pitch control, metrics, moments, counterfactuals) → store
  → MCP server (read-only stats tools)
  → Agents: Analyst → Explainer → Verifier ⟲ → Narrative → Personalizer → Verifier (per language)
  → store (insights, personalized texts, overlay cues, agent_runs)
  → FastAPI (REST + SSE replay) → React web app
```

## Two lanes (Constitution VII)
- **Fast lane:** deterministic overlay cues, emitted at their `t_in` from the store, ≤ 1 s after their event.
- **Insight lane:** verified agent output, ≤ 10 s after its moment. Judges see precomputed replays; live regeneration is rate-limited.

## Components
| Component | Runs where | Status |
|---|---|---|
| Engine + stats + build CLI | Local / CI / build job | wip (engine level 3, pitch control, xT done) |
| API + MCP (one container, `/mcp` mount) | Azure Container Apps | planned |
| Web | Azure Static Web Apps | planned |
| Models | Microsoft Foundry deployment (`gpt-4.1-mini`) | planned |
| Telemetry | Application Insights (OpenTelemetry) | planned |

## Invariants
1. Agents never compute numbers; the Verifier's deterministic number check cannot be overridden.
2. Everything is reproducible from `seed` + scenario + engine version.
3. A template fallback exists for every visible text.
