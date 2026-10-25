from functools import cache

import numpy as np
import pytest

from matchmind.engine.lineup import match_meta
from matchmind.engine.simulate import simulate_match
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.schemas import Event, MatchData, PlayerPos, TrackingFrame
from matchmind.stats.speed import (
    AlertThresholds,
    alerts,
    ball_speed,
    player_motion,
    shot_speed_kmh,
)


def _event(**kw: object) -> Event:
    base: dict[str, object] = {"event_id": "m-e00001", "match_id": "m", "period": 1, "t": 10.0,
                               "type": "pass", "team_id": "h", "player_id": "h-1", "x": 40.0,
                               "y": 34.0, "end_x": 70.0, "end_y": 34.0, "outcome": True,
                               "receiver_id": "h-2", "ball_speed_ms": None,
                               "extras": {}}  # fmt: skip
    base.update(kw)
    return Event(**base)  # type: ignore[arg-type]


def test_ball_speed_from_event_or_flight_time() -> None:
    assert ball_speed(_event(ball_speed_ms=17.5)) == 17.5
    assert ball_speed(_event(extras={"arrival_t": 12.0})) == pytest.approx(15.0)  # 30 m in 2 s
    assert ball_speed(_event()) is None
    assert shot_speed_kmh(_event(type="shot", ball_speed_ms=25.0)) == pytest.approx(90.0)


def _frames(speeds: list[float], period: int = 1, pid: str = "h-1") -> list[TrackingFrame]:
    """One player running along x at the given speed each 0.1 s frame."""
    frames, x = [], 10.0
    for k, v in enumerate(speeds):
        if k:
            x += v * 0.1
        p = PlayerPos(player_id=pid, team_id="h", x=x, y=30.0, vx=v, vy=0.0)
        frames.append(TrackingFrame(match_id="m", frame=k, period=period, t=round(k * 0.1, 1),
                                    ball=(50.0, 34.0, 0.11), players=[p]))  # fmt: skip
    return frames


def test_player_motion() -> None:
    speeds = [5.0] * 100 + [8.0] * 30 + [5.0] * 100
    m = player_motion(_frames(speeds), "h-1", (2, 0.0))
    assert m.distance_m == pytest.approx(sum(speeds[1:]) * 0.1)
    assert m.top_speed_ms == 8.0 and m.sprints == 1
    early = player_motion(_frames(speeds), "h-1", (1, 9.9))  # before the sprint
    assert early.sprints == 0 and early.top_speed_ms == 5.0
    assert early.distance_m == pytest.approx(99 * 5.0 * 0.1)
    assert player_motion(_frames(speeds), "nobody", (2, 0.0)).distance_m == 0.0


def test_sprint_alert_fires_once() -> None:
    frames = _frames([5.0] * 20 + [8.0] * 30 + [5.0] * 20)  # a 3 s sprint from t = 2.0
    cues = alerts(frames, (1, 7.0))
    speed = [c for c in cues if c.kind == "speed_alert"]
    assert len(speed) == 1
    assert speed[0].t_in == pytest.approx(2.9)  # once the run has lasted 1 s
    assert speed[0].payload == {"player_id": "h-1", "speed_ms": 8.0}
    tags = [c for c in cues if c.kind == "name_tag"]
    assert len(tags) == 1 and tags[0].t_in == speed[0].t_in
    assert alerts(frames, (1, 2.5)) == []  # not yet


def test_two_sprints_two_alerts() -> None:
    frames = _frames([8.0] * 15 + [4.0] * 10 + [8.0] * 15)
    assert len([c for c in alerts(frames, (1, 10.0)) if c.kind == "speed_alert"]) == 2


def test_distance_alert_each_km() -> None:
    frames = _frames([7.0] * 3700)  # 7 m/s for 370 s: about 2.59 km
    cues = [c for c in alerts(frames, (1, 400.0)) if c.kind == "distance_alert"]
    assert [c.payload["distance_m"] for c in cues] == [1000, 2000]
    assert cues[0].t_in == pytest.approx(142.9, abs=0.1)
    custom = alerts(frames, (1, 400.0), AlertThresholds(distance_step_m=500))
    assert len([c for c in custom if c.kind == "distance_alert"]) == 5


def test_cue_ids_are_unique() -> None:
    frames = _frames([8.0] * 15 + [4.0] * 10 + [8.0] * 15)
    cues = alerts(frames, (1, 10.0))
    assert len({c.cue_id for c in cues}) == len(cues)
    assert all(c.t_out > c.t_in for c in cues)


@cache
def _engine_match() -> MatchData:
    league = build_league()
    return simulate_match(match_meta(league, build_fixtures(league, seed=2026)[0], seed=7), level=3)


def test_motion_agrees_with_floodlight() -> None:
    """Distance and top speed agree with floodlight's kinematics models within 2%."""
    from floodlight.core.xy import XY
    from floodlight.models.kinematics import DistanceModel, VelocityModel

    data = _engine_match()
    players = [p.player_id for p in data.meta.home_squad[1:6] + data.meta.away_squad[1:6]]
    for pid in players:
        ours = player_motion(data.frames, pid, (2, 1e9))
        dist, top = 0.0, 0.0
        for period in (1, 2):
            pts = [(p.x, p.y) for f in data.frames if f.period == period
                   for p in f.players if p.player_id == pid]  # fmt: skip
            xy = XY(xy=np.array(pts, dtype=float), framerate=10)
            dm = DistanceModel()
            dm.fit(xy, difference="backward")
            dist += float(np.nansum(dm.distance_covered().property))
            vm = VelocityModel()
            vm.fit(xy, difference="backward")
            top = max(top, float(np.nanmax(vm.velocity().property)))
        assert ours.distance_m == pytest.approx(dist, rel=0.02), pid
        assert ours.top_speed_ms == pytest.approx(top, rel=0.02), pid
