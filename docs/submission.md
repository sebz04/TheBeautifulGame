# MatchMind: submission

The text submitted to the Inside the Game Hackathon 2026, kept here for reference.

| Field | Value |
|---|---|
| Project | MatchMind |
| Tagline | MatchMind: your match, your pundit. Every number verified. |
| Code | https://github.com/sebz04/TheBeautifulGame |
| Live demo | https://ca-matchmind-api.wonderfulocean-49523812.northcentralus.azurecontainerapps.io (free, no sign-in, through Nov 10, 2026) |
| Video | https://youtu.be/NuJLPVg5loM |
| Team | Sebastian Zapata (solo) |

**Keywords:** multi-agent AI, Microsoft Foundry, Microsoft Agent Framework, Model Context Protocol (MCP), football analytics, sports AI, personalization, verification, hallucination prevention, explainable AI, synthetic data, expected threat (xT), pitch control, multilingual, Azure Container Apps, Azure SQL, Azure Blob Storage, Application Insights, managed identity, GitHub Actions

**Microsoft and Azure technologies:** Microsoft Foundry (gpt-4.1-mini), Microsoft Agent Framework, Azure Container Apps, Azure SQL Database, Azure Blob Storage, Application Insights, managed identity, GitHub Actions with OIDC.

**How to test:** no sign-in. Pick a club → Start watching → press play. Then try Scout, العربية, Ask why, and Best plays. The full tour is in the [README](../README.md#for-judges-a-two-minute-tour).

## The problem

Everyone gets the same match commentary: the same story, in the same voice and language, at the same depth. A casual fan of one club and a scout studying a team's press want very different things. AI commentary could fill that gap, but language models get numbers wrong. They invent stats, credit the wrong team with a number, or call a 1–2 deficit a lead. In sports analysis, one wrong number ruins trust.

## What MatchMind does

MatchMind is a live match companion. You pick your club, press play, and a pundit explains each key moment as it happens, written for you:

- **Your club's view:** the site takes on your club's colors, and the insights are written from your side.
- **Fan or Scout:** fans get the story. Scouts also get the numbers behind each insight and advice on what the team should do next.
- **Player or Team:** follow one player or the whole side.
- **Five languages:** English, Spanish, Portuguese, French and Arabic. Arabic reads fully right to left, and each translation is checked again in its own language.
- **Ask why:** every insight shows its evidence. You see the numbers it rests on, the moments it cites, and a pitch view of the pass that was played next to the better option the analysis found.
- **Best Plays:** a tab that collects the match's decisive decisions while the match keeps playing.
- **Full-time recap:** at the final whistle, the story of the match in your language.
- **Ask the pundit live:** ask for a fresh analysis on demand, with a trace you can follow.

## How it works

Code computes every number, agents explain them, and nothing reaches the screen unverified.

1. **Match engine.** A fictional 20-club league is simulated play by play, with player tracking at 10 Hz. There is no real match data and no real clubs or players.
2. **Stats layer.** Expected threat, pitch control, pressing (PPDA), momentum and key-moment detection, stored in Azure SQL and Blob Storage. An MCP server offers them as tools.
3. **Five agents on Microsoft Foundry**, run as a Microsoft Agent Framework workflow:
   - The **Tactical Analyst** finds the moments that mattered.
   - The **Explainer** writes each insight from the stats tools.
   - The **Verifier** checks the insight in two stages. First, code recomputes every number and checks that it belongs to the right team, matches the scoreline, and doesn't misread pressing stats. Then a model judges the wording. A failed insight goes back for a rewrite, or is replaced by a template built only from verified numbers.
   - The **Narrative** agent writes the full-time recap.
   - The **Personalizer** rewrites each insight for your club, role and language.
4. **Delivery.** A FastAPI backend streams the insights beside a React replay, deployed on Azure Container Apps.

## Results

- The Verifier caught **20 of 20 planted errors** in the golden test set, with precision 1.00 ([evals](evals.md)).
- About **960 automated tests** run on every push.
- **No API keys anywhere.** One managed identity reaches SQL, Blob Storage and Foundry. GitHub Actions deploys with OIDC, so the repo stores no secrets.
- **Every agent run is traced** in Application Insights, with token counts.
- **Live and public:** no sign-in, and it stays up through November 10, 2026.

## Goals

1. **Personal analysis.** Turn one match into many stories, each for its reader: their club, their level of detail, their language.
2. **Trust by design.** Make AI sports analysis that can be checked. Deterministic code owns the numbers, and a verifier stands between the model and the screen.
3. **Explainability.** Every claim shows its work. "Ask why" is part of the product, not a debug feature.
4. **Responsible data.** Show that the whole pipeline works on synthetic data, with no real players' data and no licensed match feeds.
5. **Production quality on a student budget.** Keyless, traced and auto-deployed on Azure, within $100 of credit.
