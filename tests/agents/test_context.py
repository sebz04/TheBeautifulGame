from conftest import moment

from matchmind.agents.context import match_names, moment_context
from matchmind.engine.lineup import match_meta
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league


def test_match_names_cover_both_clubs_and_squads() -> None:
    league = build_league()
    meta = match_meta(league, build_fixtures(league, seed=2026)[0], seed=7)
    names = match_names(meta)
    assert names[meta.home.club_id] == meta.home.name
    assert names[meta.away_squad[0].player_id] == meta.away_squad[0].name
    assert len(names) == 2 + len(meta.home_squad) + len(meta.away_squad)


def test_moment_context_has_minute_labels() -> None:
    m = moment(1, period=2, t_start=600.0, t_end=638.5)
    ctx = moment_context(m)
    assert (ctx["minute_start"], ctx["minute_end"]) == ("56'", "56'")
    assert ctx["moment_id"] == "m1" and ctx["kind"] == "big_chance" and ctx["t_end"] == 638.5


def test_moment_context_has_an_events_window_of_at_least_five_minutes() -> None:
    point = moment_context(moment(1, period=1, t_start=1200.0, t_end=1200.0))
    assert point["events_window"] == {"period": 1, "t_from": 900.0, "t_to": 1200.0}
    early = moment_context(moment(1, period=2, t_start=30.0, t_end=60.0))
    assert early["events_window"] == {"period": 2, "t_from": 0.0, "t_to": 60.0}
    long = moment_context(moment(1, period=1, t_start=100.0, t_end=900.0))
    assert long["events_window"]["t_from"] == 100.0
