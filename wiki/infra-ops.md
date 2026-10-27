# Infrastructure and Operations

**Status:** Azure for Students and Foundry set up (TASK-16.1); infrastructure as code with azd + Bicep (TASK-24.1).

## Accounts
- Azure for Students ($100 credit). Budget alerts at $25 and $50.
- Foundry: the subscription's default project and resource (not renamed), with a `gpt-4.1-mini` deployment (Global Standard). **TPM quota: 200,000 tokens per minute.** The precompute throttle (`--tpm`, TASK-20) uses this.
- **Region: North Central US.** Azure for Students only allows a few regions (policy "Allowed resource deployment regions"). Create every resource there, including Application Insights and its Log Analytics workspace. Central US is blocked: `RequestDisallowedByAzure`.
- Sign-in is keyless (`DefaultAzureCredential`): `az login` locally, managed identity in Azure. Your account needs the **Azure AI User** role on the Foundry resource. There are no API keys.

## Azure deployment (`azure.yaml`, `infra/`)
- **`azd up`** provisions `infra/main.bicep` (subscription scope) and deploys the `api` service: one image with the API, the website, and `/mcp`, **built in Azure Container Registry** (`remoteBuild: true`; no local Docker).
- **Resources** (`rg-<env>`, North Central US): Container Apps environment + `ca-matchmind-api` (0.5 vCPU, 1 GiB, exactly 1 replica: always on, and the live-run limits are per replica); Container Registry (Basic); Storage (`tracking` container, shared keys off); Azure SQL server **in Canada Central** (`SQL_LOCATION`; North Central US stopped accepting new SQL servers: `RegionDoesNotAllowProvisioning`) (Entra ID sign-in only, the deployer is admin) with database `matchmind` on **Basic** (about $5/month, always on: the free serverless tier pauses, and its first request after an idle hour waits about a minute); Log Analytics + Application Insights; a user-assigned managed identity.
- **Identity:** the one managed identity pulls images (AcrPull), reads blobs (Storage Blob Data Reader), reads/writes SQL (a database user, granted by `scripts/seed_cloud.py`), and calls Foundry (Azure AI User and Cognitive Services OpenAI User on the existing Foundry account, `modules/foundry-access.bicep`). The container gets `AZURE_CLIENT_ID` so `DefaultAzureCredential` uses it. Azure SQL connections add an Entra token per connection (`store/db.py` `make_engine`; pyodbc + ODBC Driver 18 in the image).
- **Budget:** `modules/budget.bicep`, $50 a month with email alerts at 50% and 100% ($25, $50).
- **Image** (`Dockerfile`, Debian 12): stage 1 builds the website (`npm ci && npm run build`); stage 2 installs the API with `uv sync --locked --no-dev --extra azure`, Microsoft's ODBC Driver 18 (`msodbcsql18`, EULA accepted at build time, not redistributed in the repo), `data/models`, and `web/dist`; runs as a non-root user on port 8000.
- **Image builds** (`.github/workflows/image.yml`): **Azure for Students can't run registry builds** (ACR Tasks are paused on free-credit subscriptions, so `az acr build` and azd's remote build never start), and local Docker isn't needed: GitHub Actions builds the image from a fresh checkout of the public repo and publishes `ghcr.io/sebz04/matchmind-api:<sha>` and `:latest` (public, approved by the user; no secrets inside: settings and identity are injected by Azure at runtime). Point the app at it with `az containerapp update -n ca-matchmind-api -g rg-matchmind --image ghcr.io/sebz04/matchmind-api:<sha>`.
- **Deploys** (`.github/workflows/deploy.yml`): every push to main runs `azd up` with GitHub OIDC (`azd pipeline config` sets it up; no stored secrets), then waits for `/api/health`. Skipped until the repository variables exist.
- **Seeding** (`scripts/seed_cloud.py`, run once as the SQL admin with `uv run --extra azure`): copies every table from the local database to Azure SQL, grants the app identity `db_datareader`/`db_datawriter`, and uploads the tracking files to the `tracking` container.
- **azd environment** (`.azure/`, git-ignored): `FOUNDRY_RESOURCE_ID`, `FOUNDRY_PROJECT_ENDPOINT`, `ALERT_EMAIL`, `SQL_LOCATION=canadacentral`, optional `CREATE_BUDGET=false`. The Foundry id stays out of the repo.

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
| `MATCHMIND_WEB_DIST` | The built website the API serves (default `web/dist`; skipped if missing) |

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
