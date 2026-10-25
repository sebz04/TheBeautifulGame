from matchmind.config import Settings, get_settings


def test_settings_defaults(monkeypatch):
    for var in ("MATCHMIND_DB_URL", "FOUNDRY_MODEL_DEPLOYMENT", "FOUNDRY_PROJECT_ENDPOINT"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(_env_file=None)  # a developer's .env must not leak in
    assert settings.db_url == "sqlite:///data/matchmind.db"
    assert settings.foundry_model_deployment == "gpt-4.1-mini"
    assert settings.foundry_project_endpoint is None


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("MATCHMIND_DB_URL", "sqlite://")
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT", "my-deploy")
    settings = Settings(_env_file=None)
    assert settings.db_url == "sqlite://"
    assert settings.foundry_model_deployment == "my-deploy"


def test_get_settings_is_cached():
    get_settings.cache_clear()
    assert get_settings() is get_settings()


def test_blank_env_lines_keep_the_defaults(tmp_path, monkeypatch):
    """A .env copied from .env.example has blank values; they must not override defaults."""
    for var in ("MATCHMIND_DB_URL", "MATCHMIND_DATA_DIR", "MATCHMIND_BLOB_ACCOUNT_URL"):
        monkeypatch.delenv(var, raising=False)
    env = tmp_path / ".env"
    env.write_text("MATCHMIND_DB_URL=\nMATCHMIND_DATA_DIR=\nMATCHMIND_BLOB_ACCOUNT_URL=\n")
    settings = Settings(_env_file=env)
    assert settings.db_url == "sqlite:///data/matchmind.db"
    assert str(settings.data_dir) == "data"
    assert settings.blob_account_url is None
