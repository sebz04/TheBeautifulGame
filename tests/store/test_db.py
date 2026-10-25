from functools import cache

import pytest

from matchmind.engine.lineup import match_meta
from matchmind.engine.simulate import simulate_match
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.league.season import MatchResult, Season, standings
from matchmind.schemas import Claim, Insight, MatchData, Moment, OverlayCue, PersonalizedText
from matchmind.stats.player_lines import PlayerMatchLine
from matchmind.store.db import AgentRun, MetricRow, Repo


@cache
def _match() -> MatchData:
    league = build_league()
    meta = match_meta(league, build_fixtures(league, seed=2026)[0], seed=7)
    return simulate_match(meta, level=3, tracking=False)


def _repo() -> Repo:
    return Repo("sqlite:///:memory:")


def _moment(n: int, t: float, kind: str = "goal") -> Moment:
    data = _match()
    return Moment(
        moment_id=f"{data.meta.match_id}-m{n:03d}",
        match_id=data.meta.match_id,
        period=1,
        t_start=t,
        t_end=t,
        kind=kind,
        level="player",  # type: ignore[arg-type]
        team_id=data.meta.home.club_id,
        player_id=None,
        trigger_metric="goal",
        trigger_value=1.0,
        event_ids=["e1"],
    )


def test_repo_roundtrip_sqlite_memory() -> None:
    repo, data = _repo(), _match()
    repo.save_match_data(data)
    mid = data.meta.match_id
    assert repo.get_match_meta(mid) == data.meta
    assert repo.get_events(mid) == data.events
    window = repo.get_events(mid, t_from=(1, 600.0), t_to=(1, 900.0), types=("pass", "shot"))
    expected = [
        e
        for e in data.events
        if (1, 600.0) <= (e.period, e.t) <= (1, 900.0) and e.type in ("pass", "shot")
    ]
    assert window == expected and window
    assert repo.list_matches() == [mid]


def test_save_match_replaces_rows() -> None:
    repo, data = _repo(), _match()
    repo.save_match_data(data)
    repo.save_match_data(data)
    assert len(repo.get_events(data.meta.match_id)) == len(data.events)


def _rows(mid: str) -> list[MetricRow]:
    return [
        MetricRow(
            match_id=mid,
            period=p,
            t=t,
            scope="team",
            scope_id="h",
            name="ppda",
            value=v,
            kind="grid",
        )
        for p, t, v in ((1, 0.0, 9.0), (1, 30.0, 8.0), (1, 60.0, 7.5), (2, 0.0, 12.0))
    ]


def test_get_metric_latest_before_t() -> None:
    repo, mid = _repo(), _match().meta.match_id
    repo.save_metrics(mid, _rows(mid))
    assert repo.get_metric(mid, "ppda", "team", "h", (1, 45.0)) == 8.0
    assert repo.get_metric(mid, "ppda", "team", "h", (1, 60.0)) == 7.5
    assert repo.get_metric(mid, "ppda", "team", "h", (2, 10.0)) == 12.0
    assert repo.get_metric(mid, "ppda", "team", "h", (1, -1.0)) is None
    assert repo.get_metric(mid, "ppda", "team", "other", (2, 10.0)) is None
    assert repo.get_metric(mid, "missing", "team", "h", (2, 10.0)) is None
    repo.save_metrics(mid, _rows(mid))  # replaces, doesn't duplicate
    assert len(repo.list_metrics(mid)) == 4


def test_moments_insights_cues_runs() -> None:
    repo, data = _repo(), _match()
    mid = data.meta.match_id
    moments = [_moment(1, 300.0), _moment(0, 100.0, "big_chance")]
    repo.save_moments(mid, moments, details={moments[0].moment_id: {"p_value": 0.001}})
    listed = repo.list_moments(mid)
    assert [m.moment_id for m in listed] == [f"{mid}-m000", f"{mid}-m001"]  # time order
    assert repo.moment_details(moments[0].moment_id) == {"p_value": 0.001}
    insight = Insight(
        insight_id="i1",
        moment_id=moments[0].moment_id,
        match_id=mid,
        level="player",
        headline="h",
        why="w",
        recommendation="r",
        claims=[Claim(text="t", metric="xg", value=0.3, unit="xG", ref="e1")],
        event_ids=["e1"],
        confidence="high",
        verified=True,
        source="agent",
        trace_id=None,
        prompt_version="v1",
    )
    repo.save_insight(insight)
    repo.save_insight(insight)  # upsert
    assert repo.list_insights(mid) == [insight]
    texts = [
        PersonalizedText(
            insight_id="i1", persona="casual", lang=lang, headline="h", body="b", verified=True
        )
        for lang in ("en", "es")
    ]
    repo.save_personalized(texts)
    assert repo.list_personalized(mid, persona="casual", lang="es") == [texts[1]]
    assert repo.list_personalized(mid, persona="analyst", lang="es") == []
    cues = [
        OverlayCue(
            cue_id="c1",
            match_id=mid,
            period=1,
            t_in=10.0,
            t_out=14.0,
            kind="speed_alert",
            priority=2,
            payload={"player_id": "p"},
        )
    ]
    repo.save_cues(mid, cues)
    assert repo.list_cues(mid) == cues
    run = AgentRun(
        run_id="r1",
        agent="explainer",
        moment_id=moments[0].moment_id,
        status="ok",
        attempts=1,
        latency_ms=850,
        trace_id="tr",
        error=None,
    )
    repo.log_agent_run(run)
    assert repo.list_agent_runs(moments[0].moment_id) == [run]


def test_delete_match_removes_everything() -> None:
    repo, data = _repo(), _match()
    mid = data.meta.match_id
    repo.save_match_data(data)
    repo.save_metrics(mid, _rows(mid))
    repo.save_moments(mid, [_moment(0, 1.0)])
    repo.delete_match(mid)
    assert repo.list_matches() == [] and repo.get_events(mid) == []
    assert repo.list_metrics(mid) == [] and repo.list_moments(mid) == []


def test_season_tables() -> None:
    repo = _repo()
    r = MatchResult(
        match_id="r01-a-v-b",
        round=1,
        date="2026-08-15",
        home_id="a",
        away_id="b",
        home_goals=2,
        away_goals=0,
    )
    line = PlayerMatchLine(
        match_id="r01-a-v-b", round=1, player_id="p", club_id="a", minutes=90, goals=2
    )
    season = Season(
        rounds=1,
        results=[r],
        standings=standings([r], ["a", "b"]),
        player_lines=[line],
        milestones={"p": ["hat-trick"]},
        discipline={},
        unavailable={"r01-a-v-b": set()},
    )
    repo.save_season(season)
    repo.save_season(season)
    back = repo.load_season()
    assert back is not None
    assert back.results == [r] and back.player_lines == [line]
    assert back.standings == season.standings and back.milestones == {"p": ["hat-trick"]}


def test_unknown_match_is_empty() -> None:
    repo = _repo()
    assert repo.get_match_meta("nope") is None and repo.list_moments("nope") == []
    with pytest.raises(ValueError):
        repo.get_events("nope", t_from=(2, 0.0), t_to=(1, 0.0))  # empty window


def test_single_lookups() -> None:
    repo, data = _repo(), _match()
    mid = data.meta.match_id
    repo.save_match_data(data)
    e = data.events[42]
    assert repo.get_event(e.event_id) == e and repo.get_event("nope") is None
    m = _moment(0, 100.0)
    repo.save_moments(mid, [m], details={m.moment_id: {"p_value": 0.002}})
    assert repo.get_moment(m.moment_id) == m and repo.get_moment("nope") is None
    rows = _rows(mid) + [MetricRow(match_id=mid, period=1, t=30.0, scope="team", scope_id="h",
                                   name="ppda", value=8.0, kind="moment")]  # fmt: skip
    repo.save_metrics(mid, rows)
    snap = repo.get_snapshot(mid, 1, 30.0, kind="moment")
    assert [(r.name, r.value, r.kind) for r in snap] == [("ppda", 8.0, "moment")]
    assert repo.get_snapshot(mid, 1, 31.0, kind="moment") == []


def test_agent_runs_keep_tokens_and_list_by_match(tmp_path) -> None:
    from matchmind.schemas import AgentRun

    repo = Repo(f"sqlite:///{tmp_path}/a.db")
    run = AgentRun(run_id="r1", agent="explainer", moment_id="x1-m001", status="ok",
                   attempts=1, latency_ms=900, trace_id=None, error=None, tokens_in=1200,
                   tokens_out=300)  # fmt: skip
    repo.log_agent_run(run)
    assert repo.list_agent_runs("x1-m001") == [run]


def test_old_agent_runs_table_gets_token_columns(tmp_path) -> None:
    from sqlalchemy import create_engine, text

    url = f"sqlite:///{tmp_path}/old.db"
    with create_engine(url).begin() as c:  # the TASK-14 table, before token counts
        c.execute(text("CREATE TABLE agent_runs (run_id VARCHAR(96) PRIMARY KEY, "
                       "agent VARCHAR(32), moment_id VARCHAR(96), status VARCHAR(16), "
                       "attempts INTEGER, latency_ms INTEGER, trace_id VARCHAR(96), "
                       "error TEXT)"))  # fmt: skip
    from matchmind.schemas import AgentRun

    repo = Repo(url)
    run = AgentRun(run_id="r1", agent="a", moment_id="m", status="ok", attempts=1, latency_ms=1,
                   trace_id=None, error=None, tokens_in=5, tokens_out=2)  # fmt: skip
    repo.log_agent_run(run)
    assert repo.list_agent_runs("m")[0].tokens_in == 5


def test_live_lines_and_recap(tmp_path) -> None:
    from matchmind.schemas import Claim, Recap

    repo = Repo(f"sqlite:///{tmp_path}/n.db")
    repo.save_live_line("x1", "x1-m001-ins", "Laureles' press fades.")
    repo.save_live_line("x1", "x1-m002-ins", "Morejo again!")
    assert repo.list_live_lines("x1") == {"x1-m001-ins": "Laureles' press fades.",
                                          "x1-m002-ins": "Morejo again!"}  # fmt: skip
    claim = Claim(text="t", metric="xg", value=0.4, unit="", ref="r")
    recap = Recap(match_id="x1", title="T", paragraphs=["p"], key_numbers=[claim],
                  verified=True, source="agent")  # fmt: skip
    assert repo.get_recap("x1") is None
    repo.save_recap(recap)
    assert repo.get_recap("x1") == recap


def test_clear_agent_outputs(tmp_path) -> None:
    from matchmind.schemas import AgentRun, Recap

    repo = Repo(f"sqlite:///{tmp_path}/c.db")
    repo.save_live_line("x1", "x1-m001-ins", "line")
    repo.save_live_line("x2", "x2-m001-ins", "other match")
    repo.save_recap(Recap(match_id="x1", title="T", paragraphs=["p"], key_numbers=[],
                          verified=True, source="template"))  # fmt: skip
    repo.log_agent_run(AgentRun(run_id="r", agent="a", moment_id="x1-m001", status="ok",
                                attempts=1, latency_ms=1, trace_id=None, error=None))  # fmt: skip
    repo.clear_agent_outputs("x1")
    assert repo.list_live_lines("x1") == {} and repo.get_recap("x1") is None
    assert repo.list_match_runs("x1") == [] and repo.list_insights("x1") == []
    assert repo.list_live_lines("x2") == {"x2-m001-ins": "other match"}


def test_passed_moments(tmp_path) -> None:
    repo = Repo(f"sqlite:///{tmp_path}/p.db")
    repo.save_passed_moments("x1", ["x1-m001", "x1-m003"])
    repo.save_passed_moments("x2", ["x2-m001"])
    assert repo.list_passed_moments("x1") == {"x1-m001", "x1-m003"}
    repo.clear_agent_outputs("x1")
    assert repo.list_passed_moments("x1") == set()
    assert repo.list_passed_moments("x2") == {"x2-m001"}
