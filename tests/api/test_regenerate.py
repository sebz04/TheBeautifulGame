"""TASK-21.3: regenerate with rate limits, the /mcp mount, and CORS."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp.types import LATEST_PROTOCOL_VERSION

from matchmind.agents.orchestrator import Regenerated, template_insight
from matchmind.agents.templates import render
from matchmind.api.app import create_app
from matchmind.api.ratelimit import RateLimiter
from matchmind.config import Settings
from matchmind.schemas import AgentRun, Lang, Variant

Built = Any  # tests/api/conftest.py's Built
WEB = "https://matchmind.azurestaticapps.net"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def calls() -> list[tuple[str, Variant, str]]:
    return []


@pytest.fixture
def api(built: Built, clock: Clock, calls: list) -> Iterator[TestClient]:
    async def fake(moment_id: str, variant: Variant, lang: Lang) -> Regenerated:
        calls.append((moment_id, variant, lang))
        moment = built.repo.get_moment(moment_id)
        insight = template_insight(moment, moment.level, {})
        run = AgentRun(run_id="x", agent="explainer", moment_id=moment_id, status="ok",
                       attempts=1, latency_ms=5, trace_id="t1", error=None)  # fmt: skip
        return Regenerated(insight, render(insight, variant, lang, {}), [run])

    settings = Settings(_env_file=None, web_origin=WEB, api_host="testserver")  # type: ignore[call-arg]
    app = create_app(repo=built.repo, store=built.store, settings=settings,
                     limiter=RateLimiter(per_ip=5, global_=8, clock=clock),
                     regenerator=fake)  # fmt: skip
    with TestClient(app) as c:
        yield c


def _post(api: TestClient, built: Built, ip: str = "1.2.3.4", **body: Any) -> Any:
    payload = {"moment_id": built.insight.moment_id, "persona": "casual", "lang": "es"} | body
    url = f"/api/matches/{built.meta.match_id}/regenerate"
    return api.post(url, json=payload, headers={"X-Forwarded-For": ip})


def test_regenerate_runs_the_agents(api: TestClient, built: Built, calls: list) -> None:
    resp = _post(api, built, persona="club_fan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["insight"]["moment_id"] == built.insight.moment_id
    assert body["text"]["lang"] == "es" and body["text"]["club_id"] == built.meta.home.club_id
    assert body["agent_runs"][0]["agent"] == "explainer"
    assert calls[0][1] == Variant(persona="club_fan", club_id=built.meta.home.club_id)


def test_regenerate_rate_limited(api: TestClient, built: Built, clock: Clock) -> None:
    assert all(_post(api, built).status_code == 200 for _ in range(5))
    sixth = _post(api, built)
    assert sixth.status_code == 429
    assert 0 < sixth.json()["retry_after"] <= 3600 and sixth.headers["Retry-After"]
    assert _post(api, built, ip="5.6.7.8").status_code == 200  # another visitor
    clock.now += 3601
    assert _post(api, built).status_code == 200  # the hour has passed


def test_regenerate_global_daily_cap(api: TestClient, built: Built, clock: Clock) -> None:
    for n in range(8):
        assert _post(api, built, ip=f"10.0.0.{n}").status_code == 200
    capped = _post(api, built, ip="10.0.0.99")
    assert capped.status_code == 429 and capped.json()["retry_after"] > 3600


def test_invalid_requests_are_not_counted(api: TestClient, built: Built, calls: list) -> None:
    for _ in range(6):
        assert _post(api, built, lang="de").status_code == 422
    assert _post(api, built, moment_id="nope").status_code == 404
    assert _post(api, built, persona="player_focus").status_code == 422  # needs player_id
    assert _post(api, built).status_code == 200 and len(calls) == 1


def test_mcp_mounted(api: TestClient) -> None:
    resp = api.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": LATEST_PROTOCOL_VERSION, "capabilities": {},
                         "clientInfo": {"name": "test", "version": "1"}}},
        headers={"Accept": "application/json, text/event-stream"},
    )  # fmt: skip
    assert resp.status_code == 200 and "matchmind-stats" in resp.text


def test_cors_allows_only_the_web_app_and_localhost(api: TestClient) -> None:
    def preflight(origin: str) -> str | None:
        resp = api.options("/api/matches", headers={
            "Origin": origin, "Access-Control-Request-Method": "GET"})  # fmt: skip
        return resp.headers.get("access-control-allow-origin")

    assert preflight(WEB) == WEB
    assert preflight("http://localhost:5173") == "http://localhost:5173"
    assert preflight("https://evil.example") is None
    got = api.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in got.headers


def test_served_app_turns_tracing_on(monkeypatch: pytest.MonkeyPatch) -> None:
    import matchmind.api.app as app_module

    calls: list[object] = []
    monkeypatch.setattr(app_module, "configure_tracing", lambda s: calls.append(s) or True)
    monkeypatch.setattr(app_module, "create_app", lambda **kw: "the app")
    monkeypatch.delitem(app_module.__dict__, "app", raising=False)
    assert app_module.app == "the app"
    assert len(calls) == 1  # only the served app (tests build theirs with create_app)
