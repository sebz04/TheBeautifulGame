# Infrastructure and Operations

**Status:** planned (TASK-16.1 Azure setup by the user; TASK-24 deployment).

## Accounts
- Azure for Students ($100 credit). Budget alerts at $25 and $50.
- Foundry project with a `gpt-4.1-mini` deployment. Record the TPM quota here once it is known.

## Environment variables
| Var | Purpose |
|---|---|
| `MATCHMIND_DB_URL` | SQLAlchemy URL (default SQLite) |
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint |
| `FOUNDRY_MODEL_DEPLOYMENT` | Model deployment name (default `gpt-4.1-mini`) |
| `MATCHMIND_APPINSIGHTS_CONNECTION_STRING` | Telemetry |
| `MATCHMIND_BLOB_ACCOUNT_URL` | Tracking store in the cloud |

## Commands
_Add them as they become real (`uv run …`, `azd up`, `docker compose up`)._

## Costs
_Record the measured cost per precomputed match and the monthly run rate (from `docs/costs.md`)._
