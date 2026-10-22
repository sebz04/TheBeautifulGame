import numpy as np
import pytest

from matchmind.engine.ball import (
    GROUND_SPEED_MS,
    LOFTED_SPEED_MS,
    SHOT_SPEED_MS,
    draw_speed,
    flight,
    in_goal_mouth,
    restart_for,
)
from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH


def test_flight_duration() -> None:
    traj = flight((20.0, 34.0), (50.0, 34.0), "ground", 15.0)
    assert traj.reaches_end
    assert 2.0 <= traj.duration <= 2.6


def test_ground_ball_slows_and_stays_down() -> None:
    traj = flight((20.0, 34.0), (50.0, 34.0), "ground", 15.0)
    speeds = np.hypot(*np.diff(traj.xyz[:, :2], axis=0).T) / 0.1
    assert np.all(np.diff(speeds) <= 1e-9)  # never speeds up
    assert np.allclose(traj.xyz[:, 2], traj.xyz[0, 2])


def test_ground_pass_too_soft_stops_short() -> None:
    traj = flight((20.0, 34.0), (70.0, 34.0), "ground", 6.0)
    assert not traj.reaches_end
    assert traj.xyz[-1, 0] < 70.0


def test_positions_at_interpolates() -> None:
    traj = flight((20.0, 34.0), (50.0, 34.0), "ground", 15.0)
    assert traj.positions_at(0.0)[:2] == pytest.approx((20.0, 34.0))
    end = traj.positions_at(traj.duration)
    assert end[:2] == pytest.approx((50.0, 34.0), abs=0.05)
    mid = traj.positions_at(0.5 * traj.duration)
    assert 20.0 < mid[0] < 50.0


def test_lofted_ball_lands_near_its_target() -> None:
    traj = flight((30.0, 20.0), (70.0, 50.0), "lofted", 27.0)
    assert traj.reaches_end
    assert traj.positions_at(traj.duration)[:2] == pytest.approx((70.0, 50.0), abs=1.0)
    assert traj.xyz[:, 2].max() > 3.0  # it went over heads
    assert 1.5 < traj.duration < 4.0


def test_shot_is_fast_and_low() -> None:
    traj = flight((90.0, 34.0), (PITCH_LENGTH, 36.0), "shot", 25.0)
    assert traj.reaches_end
    assert traj.duration < 0.8
    assert traj.positions_at(traj.duration)[2] < 2.44


@pytest.mark.parametrize(
    ("kind", "bounds"),
    [("ground", GROUND_SPEED_MS), ("lofted", LOFTED_SPEED_MS), ("shot", SHOT_SPEED_MS)],
)
def test_speeds_within_ranges(kind: str, bounds: tuple[float, float]) -> None:
    rng = np.random.default_rng(1)
    speeds = [draw_speed(rng, kind, d, skill=s)  # type: ignore[arg-type]
              for d in (5.0, 20.0, 45.0, 70.0) for s in (0.0, 0.5, 1.0)]  # fmt: skip
    assert all(bounds[0] <= v <= bounds[1] for v in speeds)
    assert GROUND_SPEED_MS == (10.0, 22.0) and SHOT_SPEED_MS == (18.0, 32.0)


def test_overhit_pass_crosses_the_touchline() -> None:
    traj = flight((50.0, 60.0), (55.0, 75.0), "ground", 18.0)
    out = traj.out_of_play()
    assert out is not None
    t, point = out
    assert point[1] == pytest.approx(PITCH_WIDTH)
    assert 50.0 < point[0] < 55.0
    assert not traj.reaches_end
    assert t == pytest.approx(traj.duration)


def test_pass_inside_the_pitch_stays_in_play() -> None:
    assert flight((20.0, 34.0), (50.0, 34.0), "ground", 15.0).out_of_play() is None


def test_ball_stops_tracking_once_out() -> None:
    traj = flight((50.0, 60.0), (55.0, 75.0), "ground", 18.0)
    t, _ = traj.out_of_play()  # type: ignore[misc]
    assert traj.t[-1] <= t + 0.1 + 1e-9


def test_goal_mouth() -> None:
    assert in_goal_mouth(np.array([PITCH_LENGTH, 35.0, 1.0]))
    assert not in_goal_mouth(np.array([PITCH_LENGTH, 35.0, 2.6]))  # over the bar
    assert not in_goal_mouth(np.array([PITCH_LENGTH, 40.0, 1.0]))  # wide
    assert not in_goal_mouth(np.array([50.0, PITCH_WIDTH, 0.1]))  # touchline


@pytest.mark.parametrize("right", [True, False])
def test_out_of_play_by_last_touch(right: bool) -> None:
    # `right`: the direction the attacking team attacks. Its target goal line is at 105
    # when attacking right, 0 otherwise.
    target_line = PITCH_LENGTH if right else 0.0
    own_line = PITCH_LENGTH - target_line
    # Over the goal line the attackers aim at, last touched by a defender: corner.
    assert restart_for((target_line, 20.0), last_touch_attacks_right=not right) == "corner"
    # The same line, last touched by an attacker: goal kick.
    assert restart_for((target_line, 20.0), last_touch_attacks_right=right) == "goal_kick"
    # Over their own goal line off an attacker: corner to the other team.
    assert restart_for((own_line, 50.0), last_touch_attacks_right=right) == "corner"
    # Over a touchline: always a throw-in (to the other team).
    assert restart_for((60.0, PITCH_WIDTH), last_touch_attacks_right=right) == "throw_in"
    assert restart_for((10.0, 0.0), last_touch_attacks_right=not right) == "throw_in"


def test_deflection_slows_the_ball_and_turns_it() -> None:
    from matchmind.engine.ball import deflect

    rng = np.random.default_rng(3)
    for _ in range(100):
        direction, speed = deflect(rng, (1.0, 0.0), 25.0, "block")
        assert np.hypot(*direction) == pytest.approx(1.0)
        assert 0.0 < speed < 25.0


@pytest.mark.parametrize("kind", ["block", "parry"])
def test_deflections_can_go_behind_for_a_corner(kind: str) -> None:
    from matchmind.engine.ball import deflect

    # A shot toward the goal at x = 105, touched by a defender at 2 m from his line
    # (a keeper's parry) or 12 m out (a block). The defending team attacks left.
    at = (103.0, 33.0) if kind == "parry" else (93.0, 33.0)
    rng = np.random.default_rng(5)
    restarts = []
    for _ in range(300):
        direction, speed = deflect(rng, (1.0, 0.0), 26.0, kind)  # type: ignore[arg-type]
        end = (at[0] + 40.0 * direction[0], at[1] + 40.0 * direction[1])
        out = flight(at, end, "ground", speed).out_of_play()
        if out is not None:
            restarts.append(restart_for(out[1], last_touch_attacks_right=False))
    assert restarts.count("corner") > 15
    assert "goal_kick" not in restarts  # the defenders touched it last
