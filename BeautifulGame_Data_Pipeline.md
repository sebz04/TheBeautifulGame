# MatchMind Data Pipeline

Oct 21, 2026 · @Sebastian

MatchMind runs in nine steps, from synthetic data to the screen. The core rule throughout: **Python and SQL compute every number; Microsoft Foundry agents interpret, explain, and personalize.**

**Flow:** Synthetic Generator → Event Stream → Stats Engine → Tactical Analyst → Explainer → Verifier → Narrative → Personalization → Overlay → Screen

## 1. Generate synthetic match data

*Covers: Data Innovation*

- **What:** A seeded generator creates realistic match events (passes, shots, tackles, pressure, possession changes) plus simplified player and ball positions at regular intervals, with scripted storylines and a short fictional season history for milestones.
- **Tools:** Python (NumPy, pandas); Azure SQL Database for the season history; Azure Blob Storage for match files.
- **Foundry agent:** a **Scenario Designer agent** turns a prompt like "a comeback after a red card" into a storyline script (JSON) that the generator executes. A Python validation script checks the output against typical Premier League averages.

## 2. Ingest match events live

*Covers: Ingest*

- **What:** A replay service streams the synthetic match event by event, as if it were live.
- **Tools:** Python streamer → Azure Event Hubs → Azure Functions → Azure SQL Database.
- **Foundry agent:** an **Ingest agent** watches the stream for gaps or bad data and triggers a replay or fallback. This doubles as the failure-recovery demo for the Multi-Agent prize.

## 3. Compute real-time match intelligence

*Covers: Player ID, Pass Quality, Speed Metrics*

- **What:** Turns raw events into stats:
  - Player name tags with sprint and distance alerts
  - Pass distance, accuracy, and difficulty
  - Ball speed and shot speed
  - xT, pitch control, PPDA, field tilt, rolling momentum, and the control vs. chaos index
- **Tools:** Python (socceraction for xT, pitch control adapted from Friends of Tracking); SQL window functions for rolling stats; results stored in Azure SQL.
- **Foundry agent:** none. This step is deliberately deterministic. It is exposed as an **MCP server** so every agent fetches numbers instead of inventing them.

## 4. Interpret: find key moments and patterns

*Covers: Interpret*

- **What:** Detect moments that matter: momentum swings, pressing collapses, formation shifts, big chances.
- **Tools:** Python rule triggers (for example, momentum crosses a threshold) flag candidate moments.
- **Foundry agent:** a **Tactical Analyst agent** reviews flagged moments through MCP, adds tactical context, and decides which are worth surfacing at Game, Team, and Player level.

## 5. Explain why it matters, and what was better

*Covers: Explain Why a Moment Matters*

- **What:** For each key moment, explain its importance and run the counterfactual: score the alternative passes using pitch control × xT and find the better option.
- **Tools:** Python counterfactual scorer; results in Azure SQL.
- **Foundry agent:** an **Explainer agent** writes the "why," cites the event IDs and stats behind each claim, adds a confidence label, and produces the recommendations: "What should they do?" for Team and Player, "What to watch next" for Game.

## 6. Verify every claim

*Covers: Explainability*

- **What:** Nothing reaches the screen until its numbers match the stats store.
- **Tools:** Python number-matching checks; Azure Application Insights logs each agent's reasoning trace; Foundry evaluations for accuracy testing.
- **Foundry agent:** a **Verifier agent** compares every figure against the MCP stats, rejects wrong statements, and sends them back for regeneration. The evidence and trace power an "Ask why" panel in the app.

## 7. Generate narratives

*Covers: Narrative Generation*

- **What:** Live story lines, player performance context, milestones, and an automated full-time recap.
- **Tools:** Azure SQL season history for milestones.
- **Foundry agent:** a **Narrative agent** turns verified insights into short live lines and a full recap.

## 8. Personalize and translate

*Covers: Personalize, Multi-language storytelling*

- **What:** The same insight, retold for each persona (analyst, casual fan, favorite club, player-focus mode) in English or Spanish.
- **Tools:** User preferences in Azure SQL; Azure AI Speech for optional voice commentary; Azure AI Translator as a fallback for extra languages.
- **Foundry agent:** a **Personalization agent** adjusts depth, tone, and focus per persona and writes natively in each language. Translated output goes back through the Verifier.

## 9. Render overlays on screen

*Covers: Render*

- **What:** Decide what appears on screen, when, and for how long: tags, stat cards, freeze-frames, alerts.
- **Tools:** Timed overlay JSON → Azure Web PubSub → web frontend (animated 2D pitch with Game / Team / Player tabs and a key-moment timeline), hosted on Azure Container Apps.
- **Foundry agent:** an **Overlay Director agent** prioritizes and times overlays so the screen never gets cluttered, and outputs machine-readable JSON a broadcast system could use.

## Across all steps: orchestration

*Covers: Multiple Agents System, Microsoft Foundry*

- **Microsoft Agent Framework on Foundry** coordinates all seven agents, with handoffs between steps and retries when an agent fails.
- **Azure SQL Database** is the shared state every agent reads and writes.
- **MCP** connects agents to the stats engine.
- **Azure Container Apps**, **GitHub Actions**, and **Application Insights** handle deployment, CI, and monitoring.

## Requirement coverage

| Requirement | Step(s) |
| --- | --- |
| Ingest match events and data | 2 |
| Interpret into insight, patterns, context | 3, 4 |
| Explain why a moment matters | 5 |
| Personalize for all stakeholders | 8 |
| Real-time intelligence (Player ID, pass quality, speed) | 3 |
| Narrative generation | 7 |
| Explainability | 5, 6 |
| Data innovation | 1 |
| Multi-language storytelling | 8 |
| Multiple agents system | 1, 2, 4–9 (seven agents) |
| Microsoft Foundry implementation | All agent steps + orchestration |

**Build order:** start with only the Tactical Analyst, Explainer, Verifier, and Personalization agents. Add the Scenario Designer, Ingest, and Overlay Director agents once the core flow works end to end.
