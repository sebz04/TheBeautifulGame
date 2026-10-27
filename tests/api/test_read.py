"""TASK-21.1: the read endpoints against plan Task 21's contract."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from matchmind.schemas import Recap

Built = Any  # tests/api/conftest.py's Built (conftest modules share a name, so no import)


def test_health(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["ok"] is True and isinstance(body["version"], str)


def test_matches_list(client: TestClient, built: Built) -> None:
    rows = client.get("/api/matches").json()
    assert [r["match_id"] for r in rows] == [built.meta.match_id]
    row = rows[0]
    assert set(row) >= {"match_id", "title", "home", "away", "score", "scenario_id"}
    assert row["home"]["club_id"] == built.meta.home.club_id
    assert built.meta.home.name in row["title"] and built.meta.away.name in row["title"]
    assert set(row["score"]) == {"home", "away"}


def test_match_detail(client: TestClient, built: Built) -> None:
    body = client.get(f"/api/matches/{built.meta.match_id}").json()
    assert body["match_id"] == built.meta.match_id and len(body["home_squad"]) >= 11
    assert set(body["score"]) == {"home", "away"}
    assert body["realism"]["checks"] and isinstance(body["realism"]["ok"], bool)
    assert client.get("/api/matches/nope").status_code == 404


def test_tracking_window_cap(client: TestClient, built: Built) -> None:
    url = f"/api/matches/{built.meta.match_id}/tracking"
    frames = client.get(url, params={"period": 1, "from": 600, "to": 610}).json()["frames"]
    assert 90 <= len(frames) <= 101
    assert all(600 <= f["t"] <= 610 and f["period"] == 1 for f in frames)
    assert client.get(url, params={"period": 1, "from": 0, "to": 60}).status_code == 200
    assert client.get(url, params={"period": 1, "from": 0, "to": 60.5}).status_code == 422
    assert client.get(url, params={"period": 3, "from": 0, "to": 5}).status_code == 422
    assert client.get(url, params={"period": 1, "from": 10, "to": 5}).status_code == 422


def test_timeline(client: TestClient, built: Built) -> None:
    body = client.get(f"/api/matches/{built.meta.match_id}/timeline").json()
    keys = [(m["period"], m["t_start"]) for m in body["moments"]]
    assert keys and keys == sorted(keys)
    point = body["momentum"][0]
    assert set(point) >= {"period", "t", "home", "away"}
    assert {p["period"] for p in body["momentum"]} == {1, 2}


def test_insights_by_persona_and_lang(client: TestClient, built: Built) -> None:
    url = f"/api/matches/{built.meta.match_id}/insights"
    rows = client.get(url, params={"persona": "analyst", "lang": "es"}).json()
    assert len(rows) == 1 and rows[0]["insight"]["insight_id"] == built.insight.insight_id
    assert rows[0]["text"]["lang"] == "es" and rows[0]["text"]["headline"] == "Analyst es"


def test_insights_missing_variant_uses_the_template(client: TestClient, built: Built) -> None:
    url = f"/api/matches/{built.meta.match_id}/insights"
    away = built.meta.away
    params = {"persona": "club_fan", "lang": "en", "club_id": away.club_id}
    text = client.get(url, params=params).json()[0]["text"]
    assert text["source"] == "template" and text["club_id"] == away.club_id
    home = client.get(url, params={"persona": "club_fan", "lang": "en"}).json()[0]["text"]
    assert home["headline"] == "For the home fans"  # club_fan defaults to the home club
    ar = client.get(url, params={"persona": "casual", "lang": "ar"}).json()[0]["text"]
    assert ar["dir"] == "rtl"


@pytest.mark.parametrize(
    "params",
    [
        {"persona": "pundit", "lang": "en"},
        {"persona": "analyst", "lang": "de"},
        {"persona": "player_focus", "lang": "en"},  # needs player_id
        {"persona": "club_fan", "lang": "en", "club_id": "not-in-match"},
    ],
)
def test_insights_bad_params_422(client: TestClient, built: Built, params: dict) -> None:
    url = f"/api/matches/{built.meta.match_id}/insights"
    assert client.get(url, params=params).status_code == 422


def test_why(client: TestClient, built: Built) -> None:
    body = client.get(f"/api/insights/{built.insight.insight_id}/why").json()
    assert body["claims"][0]["ref"] == built.insight.claims[0].ref
    assert [e["event_id"] for e in body["events"]] == built.insight.event_ids
    assert body["agent_runs"][0]["agent"] == "explainer" and body["trace_id"] == "abc123"
    assert body["events"] and {"chosen", "best", "gain", "alternatives"} <= set(
        body["counterfactual"]
    )
    assert client.get("/api/insights/nope/why").status_code == 404


def test_stats_team_and_player(client: TestClient, built: Built) -> None:
    url = f"/api/matches/{built.meta.match_id}/stats"
    home = built.meta.home.club_id
    team = client.get(url, params={"scope": "team", "scope_id": home, "period": 2, "t": 600})
    body = team.json()
    assert body["metrics"]["passes"] > 0 and body["baseline"] is None
    assert body["profile"]["club_id"] == home
    pid = built.meta.home_squad[5].player_id
    player = client.get(url, params={"scope": "player", "scope_id": pid, "period": 2, "t": 600})
    body = player.json()
    assert body["profile"]["player_id"] == pid and "passes" in body["metrics"]
    assert body["baseline"]["passes"] > 0  # a season-average expectation at that time
    bad = {"scope": "team", "scope_id": "nope", "period": 1, "t": 60}
    assert client.get(url, params=bad).status_code == 404
    bad = {"scope": "league", "scope_id": home, "period": 1, "t": 60}
    assert client.get(url, params=bad).status_code == 422


def test_pitch_control(client: TestClient, built: Built) -> None:
    url = f"/api/matches/{built.meta.match_id}/pitch-control"
    body = client.get(url, params={"period": 1, "t": 600}).json()
    assert len(body["grid"]) == 21 and all(len(row) == 32 for row in body["grid"])
    assert all(0.0 <= v <= 1.0 for row in body["grid"] for v in row)
    assert body["attacking_team"] in (built.meta.home.club_id, built.meta.away.club_id)


def test_recap(client: TestClient, built: Built) -> None:
    url = f"/api/matches/{built.meta.match_id}/recap"
    body = client.get(url, params={"lang": "en", "persona": "casual"}).json()
    assert body["title"] == "A comeback" and body["source"] == "agent" and body["lang"] == "en"
    assert client.get(url, params={"lang": "xx"}).status_code == 422
    # No French recap stored: the English one, marked as English.
    assert client.get(url, params={"lang": "fr"}).json()["lang"] == "en"
    french = Recap(match_id=built.meta.match_id, title="Un renversement", paragraphs=["p"],
                   key_numbers=[], verified=True, source="agent", lang="fr")  # fmt: skip
    built.repo.save_recap(french)
    assert client.get(url, params={"lang": "fr"}).json()["title"] == "Un renversement"


def test_league(client: TestClient) -> None:
    body = client.get("/api/league").json()
    assert len(body["clubs"]) == 20
    assert len(body["players"]) >= 20 * 18 and {"player_id", "club_id"} <= set(body["players"][0])


def test_warm_start_caches_the_replay(built: Built) -> None:
    from matchmind.api.app import create_app

    app = create_app(repo=built.repo, store=built.store, warm=True)
    with TestClient(app):
        app.state.warmer.join(timeout=60)
        assert built.meta.match_id in app.state.services._replay


def test_realism_is_read_from_the_store(built: Built) -> None:
    from matchmind.api.app import create_app

    stored = built.repo.get_realism(built.meta.match_id)
    assert stored is not None  # saved by build_scenario
    fake = {"checks": [], "ok": True}
    built.repo.save_realism(built.meta.match_id, fake)
    try:
        with TestClient(create_app(repo=built.repo, store=built.store)) as c:
            assert c.get(f"/api/matches/{built.meta.match_id}").json()["realism"] == fake
    finally:
        built.repo.save_realism(built.meta.match_id, stored)


def test_insights_have_best_play_event_id(client: TestClient, built: Built) -> None:
    url = f"/api/matches/{built.meta.match_id}/insights"
    row = client.get(url, params={"persona": "analyst", "lang": "en"}).json()[0]
    assert row["best_play_event_id"] == built.insight.event_ids[0]  # the cited decision
    # An insight that cites no decision event gets null.
    plain = built.insight.model_copy(update={"insight_id": "no-decision-ins", "event_ids": []})
    built.repo.save_insight(plain)
    try:
        rows = client.get(url, params={"persona": "analyst", "lang": "en"}).json()
        by_id = {r["insight"]["insight_id"]: r for r in rows}
        assert by_id["no-decision-ins"]["best_play_event_id"] is None
    finally:
        from sqlalchemy import delete

        from matchmind.store.db import insights

        with built.repo.engine.begin() as c:
            c.execute(delete(insights).where(insights.c.insight_id == "no-decision-ins"))
