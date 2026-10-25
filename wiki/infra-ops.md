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

Blank lines (as copied from `.env.example`) keep the defaults (`env_ignore_empty`).

## Commands
- `uv run python -m matchmind.agents.runtime --ping`: one call to the Foundry deployment (about 3–4 s including sign-in).
- `uv run matchmind build --all`: build the 8 showcase matches.

## Costs
_Record the measured cost per precomputed match and the monthly run rate (from `docs/costs.md`)._
