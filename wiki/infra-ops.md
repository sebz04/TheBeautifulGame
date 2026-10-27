# Infrastructure and Operations

**Status:** **live** at https://ca-matchmind-api.wonderfulocean-49523812.northcentralus.azurecontainerapps.io (TASK-24): website, API, live replay, live re-ask (Foundry via managed identity), traces in App Insights. Automatic deploys wait for the one-time GitHub OIDC setup below.

## Accounts
- Azure for Students ($100 credit). Budget alerts at $25 and $50.
- Foundry: the subscription's default project and resource (not renamed), with a `gpt-4.1-mini` deployment (Global Standard). **TPM quota: 200,000 tokens per minute.** The precompute throttle (`--tpm`, TASK-20) uses this.
- **Region: North Central US.** Azure for Students only allows a few regions (policy "Allowed resource deployment regions"). Create every resource there, including Application Insights and its Log Analytics workspace. Central US is blocked: `RequestDisallowedByAzure`.
- Sign-in is keyless (`DefaultAzureCredential`): `az login` locally, managed identity in Azure. Your account needs the **Azure AI User** role on the Foundry resource. There are no API keys.

## Azure deployment (`azure.yaml`, `infra/`)
- **`azd provision`** applies `infra/main.bicep` (subscription scope). **Don't use `azd deploy`/`azd up` to ship code:** they push through Azure Container Registry, which this subscription can't build in or pull from without extra setup. The app runs the image from GitHub Container Registry (`apiImage`, default `ghcr.io/sebz04/matchmind-api:latest`).
- **Resources** (`rg-<env>`, North Central US): Container Apps environment + `ca-matchmind-api` (0.5 vCPU, 1 GiB, exactly 1 replica: always on, and the live-run limits are per replica); Container Registry (Basic); Storage (`tracking` container, shared keys off); Azure SQL server **in Canada Central** (`SQL_LOCATION`; North Central US stopped accepting new SQL servers: `RegionDoesNotAllowProvisioning`) (Entra ID sign-in only, the deployer is admin) with database `matchmind` on **Basic** (about $5/month, always on: the free serverless tier pauses, and its first request after an idle hour waits about a minute); Log Analytics + Application Insights; a user-assigned managed identity.
- **Identity:** the one managed identity pulls images (AcrPull), reads blobs (Storage Blob Data Reader), reads/writes SQL (a database user, granted by `scripts/seed_cloud.py`), and calls Foundry (Azure AI User and Cognitive Services OpenAI User on the existing Foundry account, `modules/foundry-access.bicep`). The container gets `AZURE_CLIENT_ID` so `DefaultAzureCredential` uses it. Azure SQL connections add an Entra token per connection (`store/db.py` `make_engine`; pyodbc + ODBC Driver 18 in the image).
- **Budget:** `modules/budget.bicep`, $50 a month with email alerts at 50% and 100% ($25, $50).
- **Image** (`Dockerfile`, Debian 12): stage 1 builds the website (`npm ci && npm run build`); stage 2 installs the API with `uv sync --locked --no-dev --extra azure`, Microsoft's ODBC Driver 18 (`msodbcsql18`, EULA accepted at build time, not redistributed in the repo), `data/models`, and `web/dist`; runs as a non-root user on port 8000.
- **Local run** (`docker-compose.yml`, TASK-25): one image `matchmind:local`, two services. `seed` runs `scripts/seed_demo.py --all --if-missing` into SQLite and Parquet on the `matchmind-data` volume (skips when the database exists); `app` waits for it, then serves the API and site on port 5173 with tracing off. No Azure or `.env` needed; only the live re-ask needs Foundry. Verified 2026-10-27: a fresh `docker compose up` served the site at http://localhost:5173 (seed about 3.6 min the first time, under 1 s after).
- **Image builds** (`.github/workflows/image.yml`): **Azure for Students can't run registry builds** (ACR Tasks are paused on free-credit subscriptions, so `az acr build` and azd's remote build never start), and local Docker isn't needed: GitHub Actions builds the image from a fresh checkout of the public repo and publishes `ghcr.io/sebz04/matchmind-api:<sha>` and `:latest` (public, approved by the user; no secrets inside: settings and identity are injected by Azure at runtime). Point the app at it with `az containerapp update -n ca-matchmind-api -g rg-matchmind --image ghcr.io/sebz04/matchmind-api:<sha>`.
- **Deploys** (`.github/workflows/deploy.yml`): after each Image build from main, it signs in with GitHub OIDC (no stored secrets), runs `az containerapp update --image ghcr.io/sebz04/matchmind-api:<sha>`, and waits for `/api/health`. **Not set up yet:** it needs an Entra app registration with a federated credential for this repo's main branch, Contributor on `rg-matchmind`, and repository variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`; until then it's skipped and deploys are the one manual `az containerapp update` command.
- **First deploy (2026-10-27):** provisioned with `azd up` (Azure SQL moved to Canada Central), seeded with `seed_cloud.py` (all 13 tables, counts equal to local; 8 tracking files), image `164b8d8` set by `az containerapp update`. Verified: `/api/health` ok, 8 matches, insights in 5 languages, stats, tracking from Blob, pitch control, why with counterfactual, SSE frames, a live re-ask in 73 s with a trace id, agent spans in App Insights (`chat gpt-4.1-mini`, `invoke_agent explainer`, MCP `tools/call`), the site at 61 fps with no console errors. A SQL firewall rule `deployer` allows the seeding Mac's IP.
- **TASK-24.4 redeploy (2026-10-27):** Azure SQL swept with `fix_scoreline.py --apply --db <Azure URL>` (dry run after: 0 left); image `c24a0ae` (lead check in the Verifier) deployed. Verified: the r01 63' card at 1–1 is now the standard summary, no lead phrases left in r01, a live re-ask on an agent-written moment returned a verified Spanish fan text with a trace id in 32 s. A re-ask on a player-deviation moment (`d000`) falls back to the template: the Explainer leaves `event_ids` empty for those (known, TASK-25.2).
- **TASK-25.2 to 25.4 redeploy (2026-10-27):** Azure SQL reseeded (finished with `--resume` after a dropped connection), image `6b13fc9` deployed, then `personalized` and `narratives` rebuilt as NVARCHAR (`--tables`). Verified: health, 8 matches, recaps in es/fr (agent) and ar, Arabic fan texts intact in all 8 matches (0 with "?"), French templates with elision, the swept r11 insight now a template.
- **Seeding** (`scripts/seed_cloud.py`, run once as the SQL admin with `uv run --extra azure`): drops and rebuilds the target's tables (so schema changes apply), copies every table from the local database to Azure SQL, grants the app identity `db_datareader`/`db_datawriter`, and uploads the tracking files to the `tracking` container. Each 5,000-row chunk commits on its own and is retried (5 times, backing off) after a dropped connection; **`--resume`** finishes a stopped copy without dropping anything (complete tables are skipped, only missing rows are added). Added 2026-10-27 after a home-network drop (`TCP Provider: Error code 0x274C`) at the last `metrics` chunk left Azure half-seeded. The site is down while a full copy runs (about half an hour on Basic).
- **`--tables personalized,narratives`** drops, rebuilds, and copies only those tables: used 2026-10-27 to move the Arabic texts to `NVARCHAR(max)` columns without recopying the 739k metric rows.
- **New IP?** The SQL firewall rule `deployer` holds one address; when your IP changes, the seed fails with error 40615: `az sql server firewall-rule update -g rg-matchmind -s <server> -n deployer --start-ip-address <ip> --end-ip-address <ip>`.
- **Seeding from a Mac:** `brew install microsoft/mssql-release/msodbcsql18` (with `HOMEBREW_ACCEPT_EULA=Y`), a SQL firewall rule for your IP, and **OpenSSL 3 at `/opt/homebrew/opt/openssl`**: the driver loads OpenSSL only from that link and supports 1.0, 1.1, and 3.0, so if Homebrew pointed it at OpenSSL 4, run `ln -sfn ../Cellar/openssl@3/<version> /opt/homebrew/opt/openssl`.
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
- **Hosting (estimate):** Container App (0.5 vCPU, 1 GiB, always on; idle-rate when quiet) about $10–20 through Nov 10; Azure SQL Basic about $5/month; Container Registry Basic about $5/month (unused; can be deleted); Storage, Log Analytics, App Insights cents. Budget alerts at $25 and $50.

## Deployment roadblocks (2026-10-27)
| Problem | Fix |
|---|---|
| North Central US refused new SQL servers | `SQL_LOCATION=canadacentral` |
| ACR builds paused on Azure for Students; azd remote build never started | GitHub Actions builds the image (`image.yml`) to GitHub Container Registry |
| Docker Desktop froze (local build hung; `azd up` blocked at `docker ps`) | No local Docker needed (see above) |
| App couldn't pull from ACR (`registries: null`) | App pulls the public GHCR image; template parameter `apiImage` |
| Seed: ODBC driver missing on the Mac | `HOMEBREW_ACCEPT_EULA=Y brew install microsoft/mssql-release/msodbcsql18` |
| Seed: `FA005` token + `Trusted_Connection` | Token hook removes `Trusted_Connection` |
| Seed: driver loaded OpenSSL 4 | Point `/opt/homebrew/opt/openssl` at OpenSSL 3 |
| Seed: `agent_runs.moment_id` too narrow (231 > 96) | Widened to 512; seed rebuilds the target schema |
