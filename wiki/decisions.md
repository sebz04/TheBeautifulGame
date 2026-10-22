# Decisions

One entry per decision: date, the decision, and why. Newest first.

- **2026-10-21 · Event-exact metrics for agents; 30 s rows only for charts.** MCP tools compute metrics at the requested `t` from data up to `t` (milliseconds), and each moment gets its own snapshot, so insights never cite a number up to 30 s stale and the Verifier checks the same values. Rolling team metrics aren't stored per event: they span minutes, so per-event rows add noise and storage, not information. Agents run per moment, not per event; that limit comes from model cost and quota.
- **2026-10-21 · League re-themed to Colombia (supersedes the LA league below).** 20 clubs named after barrios in 8 Colombian cities, so big cities give same-city derbies and names don't clash with real clubs (which are named after cities). Players are mostly Colombian with South American imports. Kept: 20 clubs and 38 rounds (not Apertura/Finalización), USD (scaled to Colombian-league values: median $0.5m, stars $5–15m), English as the default UI language with all 5 languages.
- **2026-10-21 · Rich profiles drive behavior, subtly.** Player and club attributes feed a capped modifier layer (±6%, or ±20% in scripted storylines). Career ambitions are narrative only. Active modifiers are logged so explanations cite real causes.
- **2026-10-21 · Season history simulated by the engine; per-90 baselines with shrinkage; `player_deviation` moments.** Baselines must come from the same engine as live matches, or every player looks anomalous. Flags need p < 0.01, ≥ 30 min, and expected ≥ 5, keeping the top 3 per window.
- **2026-10-21 · Money in USD. Backstory agent + Azure SQL vector search is the Phase 2 first priority.**
- **2026-10-21 · (Superseded) 20-club league named after Los Angeles neighborhoods.** Mirrors the Premier League's 20 clubs and 38 rounds, gives natural local derbies, and costs nothing at runtime (the league is deterministic). Real place names are fine; real club names and pro-team nicknames are blocklisted.
- **2026-10-21 · Wiki lives in the repo (`wiki/`), not the GitHub Wiki.** It is versioned with the code, reviewed in the same commit, and cheap to read locally.
- **2026-10-21 · Open-source policy.** Use libraries under permissive licenses only; use no real match data; never fork a complete app (rules §4.3, §4.7, §4.11). See `docs/research/open-source-review.md`.
- **2026-10-21 · azd for deployment.** Simpler OIDC setup and provisioning than hand-rolled workflows.
- **2026-10-21 · Batch personalization.** One model call per (insight, language) covers all persona variants. Club-fan texts are generated for both clubs; player-focus texts only for players named in the insight. This keeps tokens within the $100 credit and TPM quota.
- **2026-10-21 · SSE instead of Web PubSub; preferences stored in the browser instead of Azure SQL.** Lean architecture, and no personal data.
- **2026-10-21 · Tracking model: event-coupled engine, levels 2–4, built in layers.** Events and positions always agree, which pitch control and counterfactuals need.
- **2026-10-21 · Languages en/es/pt/fr/ar, generated natively.** Translator is not used in phase 1. Arabic shows RTL support.
- **2026-10-21 · Primary prize target: Best Multi-Agent System.**
- **2026-10-21 · Models only through a Foundry `gpt-4.1-mini` deployment.** Claude/ChatGPT consumer subscriptions have no API access, and judges check for Foundry use.
