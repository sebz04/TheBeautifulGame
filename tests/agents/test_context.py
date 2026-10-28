from conftest import moment

from matchmind.agents.context import match_names, moment_context
from matchmind.engine.lineup import match_meta
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.schemas import Event


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


def _ev(i: int, t: float, type_: str, team: str = "home", player: str | None = "p1",
        period: int = 1) -> Event:  # fmt: skip
    return Event(event_id=f"x1-e{i:05d}", match_id="x1", period=period, t=t, type=type_,
                 team_id=team, player_id=player, x=50, y=34, end_x=None, end_y=None,
                 outcome=True, receiver_id=None, ball_speed_ms=None)  # fmt: skip


def test_window_events_for_a_player_deviation_are_that_players_stat_events() -> None:
    from matchmind.agents.context import window_event_ids

    events = [_ev(1, 100, "carry"), _ev(2, 200, "pass"), _ev(3, 300, "carry"),
              _ev(4, 310, "carry", player="p2"), _ev(5, 2000, "carry")]  # fmt: skip
    dev = moment(1, kind="player_deviation", level="player", player_id="p1",
                 trigger_metric="dribbles", t_start=1800.0, t_end=1800.0, event_ids=[])  # fmt: skip
    assert window_event_ids(events, dev) == ["x1-e00001", "x1-e00003"]


def test_window_events_for_a_team_moment_are_the_teams_in_the_window() -> None:
    from matchmind.agents.context import window_event_ids

    events = [_ev(i, 880.0 + 10 * i, "pass") for i in range(1, 15)]
    events += [_ev(99, 1100.0, "tackle", team="away", player="q1")]
    press = moment(1, kind="pressing_collapse", team_id="home", trigger_metric="ppda_ratio",
                   t_start=1200.0, t_end=1200.0, event_ids=[])  # fmt: skip
    ids = window_event_ids(events, press)
    assert len(ids) == 8 and "x1-e00099" not in ids
    assert ids[-1] == "x1-e00014"  # the latest events, in time order
