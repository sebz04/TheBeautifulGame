import math
from functools import cache

import numpy as np
import pytest

from matchmind.engine.lineup import match_meta
from matchmind.engine.pitch import attacks_right
from matchmind.engine.simulate import simulate_match
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.schemas import Event, MatchData, PlayerPos, TrackingFrame
from matchmind.stats.passes import PassQuality, pass_quality, player_accuracy
from matchmind.stats.xt import load_xt

HOME, AWAY = "h", "a"
GRID = load_xt()


def _frame(
    away: list[tuple[float, float]], ball: tuple[float, float] = (40.0, 34.0)
) -> TrackingFrame:
    home = [(5.0, 34.0), ball, (55.0, 20.0), (75.0, 34.0)]
    players = [PlayerPos(player_id=f"{team}-{i}", team_id=team, x=x, y=y, vx=0.0, vy=0.0)
               for team, xy in ((HOME, home), (AWAY, away))
               for i, (x, y) in enumerate(xy)]  # fmt: skip
    return TrackingFrame(match_id="m", frame=0, period=1, t=10.0, ball=(*ball, 0.11),
                         players=players)  # fmt: skip


OPEN = [(100.0, 34.0), (90.0, 10.0), (90.0, 60.0)]  # away keeper and two far defenders


def _pass(end: tuple[float, float], outcome: bool = True, period: int = 1, t: float = 10.0,
          player: str = "h-1", **extras: object) -> Event:  # fmt: skip
    return Event(event_id="m-e00001", match_id="m", period=period, t=t, type="pass",  # type: ignore[arg-type]
                 team_id=HOME, player_id=player, x=40.0, y=34.0, end_x=end[0], end_y=end[1],
                 outcome=outcome, receiver_id="h-3" if outcome else None, ball_speed_ms=15.0,
                 extras=dict(extras))  # fmt: skip


def _q(
    end: tuple[float, float], away: list[tuple[float, float]] = OPEN, **kw: object
) -> PassQuality:
    return pass_quality(_pass(end, **kw), _frame(away), GRID, attacks_right=True,  # type: ignore[arg-type]
                        goalkeepers=frozenset({"h-0", "a-0"}))  # fmt: skip


def test_difficulty_monotone_distance() -> None:
    short, long_ = _q((55.0, 34.0)), _q((75.0, 34.0))
    assert short.distance_m == pytest.approx(15.0) and long_.distance_m == pytest.approx(35.0)
    assert long_.difficulty > short.difficulty


def test_defenders_in_the_lane_make_it_harder() -> None:
    blocked = [*OPEN, (50.0, 35.0), (60.0, 33.0)]
    assert _q((70.0, 34.0), blocked).difficulty > _q((70.0, 34.0)).difficulty


def test_lofted_is_harder() -> None:
    assert _q((70.0, 34.0), lofted=True).difficulty > _q((70.0, 34.0), lofted=False).difficulty


def test_edge_pass_finite() -> None:
    q = _q((105.0, 0.0))
    assert 0.0 <= q.difficulty <= 1.0 and math.isfinite(q.difficulty)
    assert q.xt_added is not None and math.isfinite(q.xt_added)


def test_failed_pass_has_no_xt() -> None:
    q = _q((70.0, 34.0), outcome=False)
    assert not q.completed and q.xt_added is None


def test_player_accuracy_up_to_a_time() -> None:
    events = [_pass((50.0, 34.0)), _pass((60.0, 30.0), outcome=False, t=20.0),
              _pass((50.0, 40.0), period=2, t=5.0), _pass((50.0, 40.0), player="h-2"),
              _pass((50.0, 40.0), outcome=False, period=2, t=900.0)]  # fmt: skip
    assert player_accuracy(events, "h-1", (1, 15.0)) == 1.0
    assert player_accuracy(events, "h-1", (1, 60.0)) == 0.5
    assert player_accuracy(events, "h-1", (2, 10.0)) == pytest.approx(2 / 3)
    assert player_accuracy(events, "h-1", (2, 1000.0)) == 0.5
    assert math.isnan(player_accuracy(events, "nobody", (2, 1000.0)))


@cache
def _engine_match() -> MatchData:
    league = build_league()
    return simulate_match(match_meta(league, build_fixtures(league, seed=2026)[0], seed=7), level=3)


def test_failed_passes_were_harder_in_a_real_match() -> None:
    data = _engine_match()
    frames = {(f.period, round(f.t, 1)): f for f in data.frames}
    home = data.meta.home.club_id
    keepers = frozenset({data.meta.home_squad[0].player_id, data.meta.away_squad[0].player_id})
    done, failed = [], []
    for e in data.events:
        if e.type != "pass" or e.end_x is None:
            continue
        right = attacks_right(e.team_id == home, e.period)
        q = pass_quality(e, frames[(e.period, e.t)], GRID, right, goalkeepers=keepers)
        assert 0.0 <= q.difficulty <= 1.0
        (done if q.completed else failed).append(q.difficulty)
        assert isinstance(e.extras.get("lofted"), bool), e.event_id
    assert np.mean(failed) > np.mean(done)
    assert any(e.extras.get("lofted") for e in data.events if e.type == "pass")
