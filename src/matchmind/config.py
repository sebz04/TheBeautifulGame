"""Runtime settings, read from the environment and an optional `.env` file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration in one place. App vars use the `MATCHMIND_` prefix."""

    model_config = SettingsConfigDict(
        env_prefix="MATCHMIND_",
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,  # blank lines copied from .env.example keep the defaults
        populate_by_name=True,
    )

    db_url: str = "sqlite:///data/matchmind.db"
    data_dir: Path = Path("data")
    appinsights_connection_string: str | None = None
    blob_account_url: str | None = None
    # Where agents reach the MCP stats server (mounted at /mcp by the API).
    mcp_url: str = "http://localhost:8000/mcp"

    # Foundry variables are read unprefixed, matching Azure tooling conventions.
    foundry_project_endpoint: str | None = Field(
        default=None, validation_alias="FOUNDRY_PROJECT_ENDPOINT"
    )
    foundry_model_deployment: str = Field(
        default="gpt-4.1-mini", validation_alias="FOUNDRY_MODEL_DEPLOYMENT"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
