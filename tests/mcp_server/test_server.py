import asyncio
import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from matchmind.engine.scenario import SCENARIO_DIR
from matchmind.league.season import MatchResult, Season, standings
from matchmind.mcp_server.server import TOOL_NAMES, build_mcp
from matchmind.pipeline.build_match import build_scenario
from matchmind.schemas import MatchData
from matchmind.stats.counterfactual import DECISION_TYPES
from matchmind.stats.metrics import metrics_at
from matchmind.stats.player_lines import PlayerMatchLine
from matchmind.stats.xt import load_xt
from matchmind.store.blob import LocalBackend, TrackingStore
from matchmind.store.db import Repo


@cache
def _env(tmp: str) -> tuple[Repo, TrackingStore, str]:
    repo, store = Repo("sqlite:///:memory:"), TrackingStore(LocalBackend(Path(tmp)))
    result = build_scenario(SCENARIO_DIR / "comeback_red_card.toml", repo, store)
    meta = repo.get_match_meta(result.match_id)
    assert meta is not None
    # A small stored season, so the baseline and season tools have data.
    home, away = meta.home.club_id, meta.away.club_id
    r = MatchResult(
        match_id="r00-x",
        round=1,
        date="2026-08-01",
        home_id=home,
        away_id=away,
        home_goals=1,
        away_goals=1,
    )
    lines = [
        PlayerMatchLine(
            match_id="r00-x",
            round=1,
            player_id=p.player_id,
            club_id=p.club_id,
            minutes=90,
            passes=40,
            forward_passes=15,
            goals=1 if n == 10 else 0,
        )
        for n, p in enumerate(meta.home_squad[:11])
    ]
    repo.save_season(
        Season(
            rounds=1,
            results=[r],
            standings=standings([r], [home, away]),
            player_lines=lines,
            milestones={home: ["top of the table"]},
            discipline={},
            unavailable={},
        )
    )
    return repo, store, result.match_id


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> tuple[Repo, TrackingStore, str]:
    return _env(str(tmp_path_factory.mktemp("tracking")))


def call(env: tuple[Repo, TrackingStore, str], tool: str, **args: Any) -> Any:
    repo, store, _ = env
    server = build_mcp(repo, store)

    async def go() -> Any:
        async with Client(server) as client:
            result = await client.call_tool(tool, args)
            assert not result.is_error, result.content
            return json.loads(result.content[0].text)  # type: ignore[union-attr]

    return asyncio.run(go())


def _data(env: tuple[Repo, TrackingStore, str]) -> MatchData:
    repo, store, mid = env
    meta = repo.get_match_meta(mid)
    assert meta is not None
    return MatchData(meta=meta, events=repo.get_events(mid), frames=store.read_all(mid))


def test_tools_listed(env: tuple[Repo, TrackingStore, str]) -> None:
    async def go() -> list[str]:
        async with Client(build_mcp(env[0], env[1])) as client:
            return [t.name for t in (await client.list_tools()).tools]

    names = asyncio.run(go())
    assert sorted(names) == sorted(TOOL_NAMES) and len(names) == 12


def test_match_summary(env: tuple[Repo, TrackingStore, str]) -> None:
    out = call(env, "get_match_summary", match_id=env[2])
    data = _data(env)
    assert out["home"]["club_id"] == data.meta.home.club_id
    goals = sum(e.type == "goal" for e in data.events)
    assert out["score"]["home"] + out["score"]["away"] == goals
    assert out["moments"] == len(env[0].list_moments(env[2])) and out["ref"] == f"match:{env[2]}"


def test_get_metric_matches_repo(env: tuple[Repo, TrackingStore, str]) -> None:
    repo, _, mid = env
    rows = [r for r in repo.list_metrics(mid) if r.kind == "grid"][::7000][:6]
    for r in rows:
        out = call(
            env,
            "get_metric",
            match_id=mid,
            name=r.name,
            scope=r.scope,
            scope_id=r.scope_id,
            period=r.period,
            t=r.t,
        )
        assert out["value"] == pytest.approx(r.value)
        assert out["ref"] == f"metric:{r.name}@{r.period}:{r.t}"


def test_team_metrics_event_exact(env: tuple[Repo, TrackingStore, str]) -> None:
    repo, _, mid = env
    data = _data(env)
    home = data.meta.home.club_id
    out = call(env, "get_team_metrics", match_id=mid, team_id=home, period=1, t=615.0)
    exact = metrics_at(data, load_xt(), 1, 615.0, "team", home)
    assert {k: v["value"] for k, v in out["metrics"].items()} == pytest.approx(exact)
    stored = repo.get_metric(mid, "passes", "team", home, (1, 615.0))  # the 600 s row
    assert stored is not None and exact["passes"] > stored
    player = data.meta.home_squad[6].player_id
    p = call(env, "get_player_stats", match_id=mid, player_id=player, period=2, t=1234.5)
    assert {k: v["value"] for k, v in p["metrics"].items()} == pytest.approx(
        metrics_at(data, load_xt(), 2, 1234.5, "player", player)
    )


def test_no_future_events(env: tuple[Repo, TrackingStore, str]) -> None:
    mid = env[2]
    out = call(
        env, "get_events", match_id=mid, period=1, t_from=300.0, t_to=600.0, types=["pass", "shot"]
    )
    assert out["events"] and all(
        300.0 <= e["t"] <= 600.0 and e["period"] == 1 and e["type"] in ("pass", "shot")
        for e in out["events"]
    )
    assert all(e["ref"] == e["event_id"] for e in out["events"])
    devs = call(env, "get_player_deviations", match_id=mid, period=1, t=2400.0)
    assert all(d["minutes_played"] <= 40.0 + 1e-6 for d in devs["deviations"])


def test_moment_and_counterfactual(env: tuple[Repo, TrackingStore, str]) -> None:
    repo, _, mid = env
    moment = repo.list_moments(mid)[0]
    out = call(env, "get_moment", moment_id=moment.moment_id)
    assert out["moment"]["moment_id"] == moment.moment_id and out["ref"] == moment.moment_id
    assert set(out["metrics_at_end"]) == {
        _data(env).meta.home.club_id,
        _data(env).meta.away.club_id,
    }
    decided = next(
        e for e in repo.get_events(mid) if e.type in DECISION_TYPES and "best_score" in e.extras
    )
    cf = call(env, "get_counterfactual", event_id=decided.event_id)
    assert cf["best"]["score"] == pytest.approx(decided.extras["best_score"], abs=1e-3)
    assert cf["gain"] >= 0 and cf["ref"] == decided.event_id and len(cf["alternatives"]) <= 5


def test_profiles_season_and_baselines(env: tuple[Repo, TrackingStore, str]) -> None:
    meta = _data(env).meta
    pid = meta.home_squad[10].player_id
    assert call(env, "get_player_profile", player_id=pid)["profile"]["player_id"] == pid
    club = call(env, "get_club_profile", club_id=meta.home.club_id)
    assert club["profile"]["club_id"] == meta.home.club_id
    season = call(env, "get_season_context", entity_id=meta.home.club_id)
    assert season["standing"]["club_id"] == meta.home.club_id
    assert season["milestones"] == ["top of the table"]
    player = call(env, "get_season_context", entity_id=pid)
    assert player["totals"]["goals"] == 1 and player["totals"]["matches"] == 1
    base = call(env, "get_player_baseline", player_id=pid)
    assert base["baseline"]["per90"]["passes"] > 0


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("get_match_summary", {"match_id": "nope"}),
        ("get_events", {"match_id": "nope", "period": 1, "t_from": 0.0, "t_to": 10.0}),
        ("get_team_metrics", {"match_id": "nope", "team_id": "x", "period": 1, "t": 10.0}),
        ("get_player_stats", {"match_id": "nope", "player_id": "x", "period": 1, "t": 10.0}),
        (
            "get_metric",
            {
                "match_id": "nope",
                "name": "xg",
                "scope": "team",
                "scope_id": "x",
                "period": 1,
                "t": 1.0,
            },
        ),
        ("get_moment", {"moment_id": "nope"}),
        ("get_counterfactual", {"event_id": "nope"}),
        ("get_season_context", {"entity_id": "nope"}),
        ("get_player_profile", {"player_id": "nope"}),
        ("get_club_profile", {"club_id": "nope"}),
        ("get_player_baseline", {"player_id": "nope"}),
        ("get_player_deviations", {"match_id": "nope", "period": 1, "t": 10.0}),
    ],
)
def test_unknown_ids_return_an_error_not_a_crash(
    env: tuple[Repo, TrackingStore, str], tool: str, args: dict[str, Any]
) -> None:
    out = call(env, tool, **args)
    assert "error" in out and out["error"]


def test_unknown_team_or_metric(env: tuple[Repo, TrackingStore, str]) -> None:
    mid = env[2]
    assert "error" in call(env, "get_team_metrics", match_id=mid, team_id="nope", period=1, t=60.0)
    assert "error" in call(
        env,
        "get_metric",
        match_id=mid,
        name="bogus",
        scope="team",
        scope_id=_data(env).meta.home.club_id,
        period=1,
        t=60.0,
    )
