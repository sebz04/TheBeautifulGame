# Infrastructure and Operations

**Status:** Azure for Students and Foundry set up (TASK-16.1); deployment is TASK-24.

## Accounts
- Azure for Students ($100 credit). Budget alerts at $25 and $50.
- Foundry: the subscription's default project and resource (not renamed), with a `gpt-4.1-mini` deployment (Global Standard). **TPM quota: 200,000 tokens per minute.** The precompute throttle (`--tpm`, TASK-20) uses this.
- **Region: North Central US.** Azure for Students only allows a few regions (policy "Allowed resource deployment regions"). Create every resource there, including Application Insights and its Log Analytics workspace. Central US is blocked: `RequestDisallowedByAzure`.
- Sign-in is keyless (`DefaultAzureCredential`): `az login` locally, managed identity in Azure. Your account needs the **Azure AI User** role on the Foundry resource. There are no API keys.

## Environment variables
Read by `src/matchmind/config.py`; template in `.env.example`. Foundry vars are unprefixed.

| Var | Purpose |
|---|---|
| `MATCHMIND_DB_URL` | SQLAlchemy URL (default `sqlite:///data/matchmind.db`) |
| `MATCHMIND_DATA_DIR` | Generated data root (default `data`) |
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint |
| `FOUNDRY_MODEL_DEPLOYMENT` | Model deployment name (default `gpt-4.1-mini`) |
| `MATCHMIND_APPINSIGHTS_CONNECTION_STRING` | Traces. The full connection string (`InstrumentationKey=…;IngestionEndpoint=…`), not the bare key. Invalid or blank: tracing is off with a warning |
| `MATCHMIND_BLOB_ACCOUNT_URL` | Tracking store in the cloud |
| `MATCHMIND_MCP_URL` | Where agents reach the MCP stats server (default `http://localhost:8000/mcp`) |
| `MATCHMIND_WEB_ORIGIN` | The Static Web App origin allowed by CORS (localhost:5173 is always allowed) |
| `MATCHMIND_API_HOST` | The API's public host name, allowed by the `/mcp` DNS-rebinding check |

Blank lines (as copied from `.env.example`) keep the defaults (`env_ignore_empty`).

## Commands
- `uv run python -m matchmind.agents.runtime --ping`: one call to the Foundry deployment (about 3–4 s including sign-in).
- `uv run matchmind build --all`: build the 8 showcase matches.
- `uv run python scripts/record_llm_fixtures.py`: run Analyst → Explainer → Verifier live on 3 moments and save the replies (`tests/fixtures/llm/`). About 1 minute.
- `uv run uvicorn matchmind.api.app:app`: the API on port 8000 (see [api-frontend.md](api-frontend.md)).
- `uv run python scripts/precompute.py --all`: precompute every match live (resumable; `--limit 1 --match <id>` for a smoke test). About 2 h and $9.50 for all 8; a re-run of finished matches takes seconds. See [orchestrator.md](orchestrator.md).
- `uv run python scripts/devui.py`: open the workflow in Agent Framework DevUI (needs the MCP server running).
- `uv run python scripts/build_verifier_golden.py`, then `uv run python scripts/run_foundry_eval.py --runs 3`: rebuild the Verifier golden set and evaluate it live (`docs/evals.md`). About 5 minutes, 84 model calls.

## Costs
- **Precompute (TASK-20.2):** $9.53 for all 8 matches, $0.79–1.45 per match (`docs/costs.md`), on `gpt-4.1-mini` list prices. Runs once; serving replays costs no tokens.
- _Monthly hosting run rate: to be measured at TASK-24._
