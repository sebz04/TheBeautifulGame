import math
from functools import cache

import numpy as np
import pytest

from matchmind.engine.lineup import match_meta
from matchmind.engine.scenario import Beat, Scenario
from matchmind.engine.simulate import simulate_match
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles
from matchmind.schemas import Event, EventType, MatchData
from matchmind.stats.team import control_chaos, field_tilt, momentum_series, ppda
from matchmind.stats.xt import load_xt

H, A = "h", "a"  # period 1: h attacks right (toward x = 105), a attacks left
WHOLE = ((1, 0.0), (2, 1e9))


class _Ev:
    def __init__(self) -> None:
        self.items: list[Event] = []

    def add(self, type_: EventType, team: str, x: float, end_x: float | None = None,
            outcome: bool | None = True, t: float | None = None, period: int = 1,
            **extras: object) -> "_Ev":  # fmt: skip
        n = len(self.items)
        self.items.append(Event(
            event_id=f"m-e{n:05d}", match_id="m", period=period,  # type: ignore[arg-type]
            t=float(n) if t is None else t, type=type_, team_id=team, player_id=f"{team}-p",
            x=x, y=34.0, end_x=end_x, end_y=None if end_x is None else 34.0, outcome=outcome,
            receiver_id=None, ball_speed_ms=None, extras=dict(extras)))  # fmt: skip
        return self


def test_ppda_known_values() -> None:
    ev = _Ev()
    for _ in range(20):
        ev.add("pass", A, 80.0, 75.0)  # a's own 60% is x > 42 in period 1
    ev.add("pass", A, 20.0, 15.0)  # in a's attacking 40%: not counted
    for type_ in ("tackle", "interception", "foul", "tackle"):
        ev.add(type_, H, 70.0)  # h's actions in a's 60%
    ev.add("tackle", H, 20.0)  # deep in h's own half: not counted
    assert ppda(ev.items, H, home_id=H, t_from=WHOLE[0], t_to=WHOLE[1]) == pytest.approx(5.0)
    assert ppda(ev.items, A, home_id=H, t_from=WHOLE[0], t_to=WHOLE[1]) is None  # no actions


def test_ppda_window() -> None:
    ev = _Ev()
    for k in range(10):
        ev.add("pass", A, 80.0, 75.0, t=float(k))
    ev.add("tackle", H, 70.0, t=5.0).add("tackle", H, 70.0, t=20.0)
    assert ppda(ev.items, H, home_id=H, t_from=(1, 0.0), t_to=(1, 9.0)) == pytest.approx(10.0)


def test_field_tilt() -> None:
    ev = _Ev()
    for _ in range(3):
        ev.add("pass", H, 80.0, 90.0)  # h's final third: x >= 70
    ev.add("pass", A, 30.0, 20.0)  # a's final third: x <= 35
    ev.add("pass", H, 40.0, 50.0)  # not in a final third
    assert field_tilt(ev.items, H, home_id=H, t_from=WHOLE[0], t_to=WHOLE[1]) == 0.75
    assert field_tilt([], H, home_id=H, t_from=WHOLE[0], t_to=WHOLE[1]) == 0.5


def test_momentum_series() -> None:
    ev = _Ev()
    ev.add("shot", H, 95.0, t=100.0, xg=0.3).add("shot", A, 10.0, t=500.0, xg=0.1)
    series = momentum_series(ev.items, load_xt(), home_id=H, window_s=300, step_s=30)
    at = {(p.period, p.t): p for p in series.points}
    assert at[(1, 120.0)].home == pytest.approx(0.3) and at[(1, 120.0)].diff > 0
    assert at[(1, 510.0)].away == pytest.approx(0.1) and at[(1, 510.0)].home == 0.0
    assert at[(1, 510.0)].diff < 0
    assert all(math.isfinite(p.diff) for p in series.points)


def _possessions(lengths: list[int], long_balls: int = 0) -> list[Event]:
    ev, team = _Ev(), H
    for n in lengths:
        for k in range(n):
            far = k < long_balls
            ev.add("pass", team, 40.0 if team == H else 65.0,
                   (80.0 if far else 50.0) if team == H else (25.0 if far else 55.0))  # fmt: skip
        team = A if team == H else H
    return ev.items


def test_control_chaos_extremes() -> None:
    calm = control_chaos(_possessions([30] * 6), [], WHOLE[0], WHOLE[1], home_id=H)
    wild = control_chaos(_possessions([3] * 60, long_balls=1), [], WHOLE[0], WHOLE[1], home_id=H)
    assert calm < 0.3 and wild > 0.7
    assert 0.0 <= calm <= 1.0 and 0.0 <= wild <= 1.0


@cache
def _ten_men() -> MatchData:
    league = build_league()
    meta = match_meta(league, build_fixtures(league, seed=2026)[0], seed=7)
    s = Scenario(scenario_id="t", title="t", home_club_id=meta.home.club_id,
                 away_club_id=meta.away.club_id, seed=7,
                 beats=[Beat(minute=20, kind="red_card", team="home")])  # fmt: skip
    return simulate_match(meta, s, level=3, profiles=build_profiles(league, seed=2026))


def test_metrics_finite_with_ten_men() -> None:
    data = _ten_men()
    home, away = data.meta.home.club_id, data.meta.away.club_id
    red = next(e for e in data.events if e.type == "card" and e.extras["card"] == "red")
    after, end = (red.period, red.t), (2, 1e9)
    for team in (home, away):
        value = ppda(data.events, team, home_id=home, t_from=after, t_to=end)
        assert value is None or math.isfinite(value)
        assert 0.0 <= field_tilt(data.events, team, home_id=home, t_from=after, t_to=end) <= 1.0
    chaos = control_chaos(data.events, data.frames, after, (red.period, red.t + 600.0), home)
    assert 0.0 <= chaos <= 1.0
    series = momentum_series(data.events, load_xt(), home_id=home)
    assert np.isfinite([p.diff for p in series.points]).all()
