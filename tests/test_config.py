from matchmind.config import Settings, get_settings


def test_settings_defaults(monkeypatch):
    for var in ("MATCHMIND_DB_URL", "FOUNDRY_MODEL_DEPLOYMENT", "FOUNDRY_PROJECT_ENDPOINT"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.db_url == "sqlite:///data/matchmind.db"
    assert settings.foundry_model_deployment == "gpt-4.1-mini"
    assert settings.foundry_project_endpoint is None


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("MATCHMIND_DB_URL", "sqlite://")
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT", "my-deploy")
    settings = Settings()
    assert settings.db_url == "sqlite://"
    assert settings.foundry_model_deployment == "my-deploy"


def test_get_settings_is_cached():
    get_settings.cache_clear()
    assert get_settings() is get_settings()
