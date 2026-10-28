# TheBeautifulGame
Inside the Game Hackathon 2026 Project Led and Authored By Sebastian Zapata

**MatchMind: your match, your pundit.** A team of AI agents watches a synthetic football match with you and explains every key moment your way: your club, your player, your language, as a fan or as a scout. Every number it says is checked against the match data before you see it, and so is who it belongs to and what it means.

Built with **Microsoft Foundry**, **Microsoft Agent Framework**, **MCP**, **Azure Container Apps**, **Azure SQL**, **Azure Blob Storage**, and **Application Insights**.

▶ **Live demo:** https://ca-matchmind-api.wonderfulocean-49523812.northcentralus.azurecontainerapps.io (free, no sign-in, available through Nov 10, 2026)

🎬 **Demo video (under 2 minutes):** link added at submission

## For judges: a two-minute tour

1. **Pick your club** on the welcome page (the whole site takes its colors), optionally a favorite player, a language, and **Fan** or **Scout**.
2. **Open a match.** Your club's matches come first. *Atlético Chapinero v Atlético Laureles* is a 3–2 comeback with a red card and a hat-trick.
3. **Press play.** Use 4× or 8× to move faster, or click a moment on the timeline. Player names and speed alerts appear on the pitch, and your pundit's insight appears on the right, written for you.
4. **Flip the switches:** Team ⇄ Player and Fan ⇄ Scout, or change the language (try العربية). The same moment is re-voiced instantly, because every version was precomputed and verified.
5. **Ask why** on any insight to see the evidence:
   - the numbers and their sources
   - the cited events
   - each agent's runs, with a trace id
   - the best alternative to the decision, drawn on the pitch
6. **Ask the pundit live** (inside Ask why) re-runs the agents on that moment in about 30 s. It's limited to 5 an hour per visitor, so Foundry costs stay bounded.
7. **Best plays:** freeze a decision and compare what the player did with the best option. The live match keeps playing in the strip at the top.
8. **Full time:** drag to about 89', play at 8×, and the recap takes over the pundit's column, in your language.

## How it meets the challenge (§4.1)

| Requirement | Where |
|---|---|
| **(i)(a) Ingest** synthetic events as they happen: passes, shots, tackles, possession changes, pressure, metadata | Match engine `src/matchmind/engine/` (`coupled.py`, `simulate.py`); store `src/matchmind/store/`; live SSE replay `src/matchmind/api/routes_live.py` |
| **(i)(b) Interpret** into statistics, patterns, and context | `src/matchmind/stats/`: xT (`xt.py`), pitch control (`pitch_control.py`), team metrics such as PPDA, field tilt, and momentum (`team.py`), key moments (`moments.py`), player deviations against season baselines (`deviations.py`, `baselines.py`); MCP server `src/matchmind/mcp_server/server.py` |
| **(i)(c) Explain** why a moment matters | Tactical Analyst and Explainer (`src/matchmind/agents/analyst.py`, `explainer.py`); the Verifier (`verifier.py`, `numbers.py`, `scoreline.py`); counterfactuals (`stats/counterfactual.py`) |
| **(i)(d) Render** alongside the match | SSE stream of frames, events, cues, and insights (`api/routes_live.py`); the site in `web/src/` (`components/Pitch.tsx`, `Overlays.tsx`, `InsightPanel.tsx`) |
| **(i)(e) Personalize**: analyst vs casual fan, favorite club, favorite player, player focus, language | Personalizer (`agents/personalizer.py`) in 4 voices × 5 languages; switches and voice mapping (`web/src/components/PersonaBar.tsx`, `web/src/persona.ts`); welcome page (`web/src/pages/Welcome.tsx`) |
| **(ii) Player identification**: name tags with speed and distance indicators at thresholds | `stats/speed.py` (`alerts`), sent at their time by the stream; `web/src/components/Overlays.tsx` |
| **(ii) Pass quality**: distance, accuracy, difficulty | `stats/passes.py` |
| **(ii) Speed metrics**: ball and shot speed | `stats/speed.py` |
| **(ii) Auto-eventing** | Events come from the engine, which is coupled to tracking: each pass, shot, and tackle is generated together with the player and ball movement that produce it. There's no video, because the data is synthetic. |
| **(iii) Narratives**: key narratives, player context, milestones, recaps | Narrative agent (`agents/narrative.py`): live lines and full-time recap with season milestones; player deviations against season baselines |
| **(iv) Explainability**: control vs chaos, pressure changes, rhythm | `stats/team.py` (`control_chaos`, PPDA, momentum), moments such as `pressing_collapse` and `momentum_swing`; "Ask why" (`web/src/components/AskWhyPanel.tsx`) |
| **(v) Data innovation**: synthetic football-realistic datasets | 20-club league with profiles and chemistry (`league/`), season history (`league/season.py`), storyline scenarios (`scenarios/`), a realism validator ([docs/realism.md](docs/realism.md): 18/18 checks over 20 seeds), Parquet tracking |
| **(vi) Multi-language storytelling** | Fan texts and full-time recaps in English, Spanish, Portuguese, French, and Arabic, each verified again in its own language (`agents/personalizer.py`, `narrative.py` `translate_recap`); interface in all five (`web/src/i18n/`), right to left for Arabic |

## How it's built

```
scenario → match engine → stats store ─→ stats engine → MCP stats server
                                                           │
             Tactical Analyst → Explainer ⟲ Verifier → Narrative → Personalizer ⟲ Verifier
                                                           │
                              FastAPI (REST, SSE live replay, live re-ask, /mcp) → React site
```

- **Multi-agent, with checks:** five specialized agents in a Microsoft Agent Framework workflow, sharing state through the store and reading numbers only through MCP tools.
  - The Verifier first runs deterministic checks in code, in all five languages: every number recomputed from its source; lead wording against the score at that moment (`scoreline.py`); each team's number given to that team, not its opponent (`owners.py`); PPDA read as a team's own pressing, never as pressure it faces (`meaning.py`). Only then does the model judge the wording against the cited events.
  - Failed texts become deterministic templates, so the screen is never blank and never wrong.
  - Transient errors are retried with backoff; every agent run is logged with tokens and traced.
- **Two lanes:** overlays (name tags, speed and distance) are computed by code and sent at their exact time. Insights are precomputed, so viewers never wait on a model.
- **Keyless on Azure:** one managed identity reads Blob Storage, signs in to Azure SQL with an Entra token, and calls Foundry. Traces go to Application Insights.
- **Shipped by GitHub Actions:** every push to `main` runs CI, builds the image, and deploys it to Container Apps, signing in to Azure with OIDC as a managed identity (no stored secrets), then checks `/api/health`.

Details: [docs/architecture.md](docs/architecture.md) · codebase map: [wiki/README.md](wiki/README.md).

## Quality and numbers

- **Tests:** about 960 automated tests (815 Python, 142 TypeScript), plus Playwright browser tests (the full fan journey, and axe accessibility at 1280 and 375 px). CI runs lint, types, tests, a license gate, the wiki check, and the browser tests on every push; multi-match statistical tests run nightly.
- **Verifier:** on a 40-insight golden set with 20 planted errors, it catches **20/20** with precision 1.00 and 0 false alarms on the 20 correct insights ([docs/evals.md](docs/evals.md)). The code checks were added after errors seen in real agent output: across 3,702 stored texts the team-number check found 18 real misattributions and 1 false alarm, and every flagged text was replaced by its verified template.
- **Realism:** the engine passes all 18 professional-range checks over 20 seeds ([docs/realism.md](docs/realism.md)).
- **Cost:** precomputing all 8 matches in 5 languages cost **$9.53** (18.3M tokens; [docs/costs.md](docs/costs.md)). Hosting runs on a $100 Azure for Students credit, with a $50 budget alert. Live questions are rate limited (5 an hour per visitor, 100 a day in all).
- **Accessibility:** WCAG AA contrast for every club's colors, full keyboard use, and usable at 375 px wide.

## Run it yourself

### On your machine (Docker, no Azure needed)

```bash
docker compose up
```

Then open http://localhost:5173.
- **First run:** it builds all 8 showcase matches with template insights, which takes a few minutes once. Later runs start right away.
- **What works offline:** everything except "Ask the pundit live", which needs Foundry.
- **The full experience:** the AI-written insights are on the live demo.

### For development

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.12) and Node 22.

```bash
uv sync                                   # Python dependencies
uv run matchmind build --all --season     # build the 8 matches (about 12 min)
uv run uvicorn matchmind.api.app:app      # API on :8000
cd web && npm ci && npm run dev           # site on :5173
uv run pytest && (cd web && npm test)     # tests
```

Writing the AI insights (`scripts/precompute.py`) and the live re-ask need a Foundry project: copy `.env.example` to `.env` and sign in with `az login` (keyless). Deploying is `azd provision` plus `az containerapp update` (see [wiki/infra-ops.md](wiki/infra-ops.md)).

## Project

- **Rules and plan:** [CONSTITUTION.md](CONSTITUTION.md) and [docs/superpowers/plans/](docs/superpowers/plans/), including what changed while building and why.
- **Data:** all of it is synthetic. The clubs, players, and matches are fictional (Colombian barrio clubs), and no real match data is used.
- **License:** MIT ([LICENSE](LICENSE)). The match data is synthetic and free to reuse with the code.
- **Credits and licenses:** every open-source dependency is listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and a CI gate checks the runtime licenses. Pitch control follows Spearman (2018) and the Friends of Tracking implementation by Laurie Shaw ([LaurieOnTracking](https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking), MIT): ours in `src/matchmind/stats/pitch_control.py` is vectorized and parity-tested against it.
