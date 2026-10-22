import numpy as np
import pytest

from matchmind.engine.kinematics import PlayerState, step_player
from matchmind.engine.roles import (
    RUN_HOVER_M,
    RoleContext,
    defensive_line,
    draw_timing_error,
    offside_line,
    role_target,
)
from matchmind.schemas import Player, PlayerPos, TrackingFrame
from matchmind.stats.pitch_control import offside_players

BALL = np.array([60.0, 30.0])


def _ctx(**kw: object) -> RoleContext:
    base: dict[str, object] = {"pos": np.array([50.0, 34.0]), "anchor": np.array([45.0, 20.0]),
                               "ball": BALL, "attacks_right": True}  # fmt: skip
    base.update(kw)
    return RoleContext(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("right", [True, False])
def test_press_goes_goal_side_of_the_ball(right: bool) -> None:
    target, urgency = role_target("press", _ctx(attacks_right=not right))
    # A defender attacking the other way protects the goal behind him.
    own_goal_x = 105.0 if right else 0.0
    assert np.hypot(*(target - BALL)) == pytest.approx(1.0, abs=1e-6)
    assert abs(target[0] - own_goal_x) < abs(BALL[0] - own_goal_x)
    assert urgency > 0.9


def test_mark_stays_goal_side_of_the_opponent() -> None:
    opponent = np.array([30.0, 40.0])
    target, _ = role_target("mark", _ctx(mark=opponent))
    assert np.hypot(*(target - opponent)) == pytest.approx(1.5, abs=1e-6)
    assert target[0] < opponent[0]  # attacking right, own goal at x = 0


def test_mark_needs_an_opponent() -> None:
    with pytest.raises(ValueError):
        role_target("mark", _ctx())


def test_cover_sits_between_ball_and_own_goal() -> None:
    target, urgency = role_target("cover", _ctx())
    assert 0.0 < target[0] < BALL[0]
    assert 0.3 <= urgency <= 0.7


def test_support_offers_an_angle_near_the_ball() -> None:
    target, _ = role_target("support", _ctx())
    assert 8.0 <= np.hypot(*(target - BALL)) <= 16.0
    assert target[1] < BALL[1]  # on the anchor's side (anchor y = 20)


def test_gk_between_ball_and_goal_inside_the_box() -> None:
    target, _ = role_target("gk_position", _ctx(ball=np.array([20.0, 50.0])))
    goal = np.array([0.0, 34.0])
    to_ball = np.array([20.0, 50.0]) - goal
    cross = to_ball[0] * (target - goal)[1] - to_ball[1] * (target - goal)[0]
    assert abs(cross) < 1e-6  # on the goal-ball line
    assert 0.0 < target[0] <= 16.5


def test_hold_line_targets_share_an_x() -> None:
    anchors_d = np.array([30.0, 31.0, 29.0, 30.5])
    line = defensive_line(anchors_d, ball_depth=60.0, line_height=0.5)
    targets = [
        role_target("hold_line", _ctx(anchor=np.array([a, y]), line_depth=line))[0]
        for a, y in zip(anchors_d, (10.0, 26.0, 42.0, 58.0), strict=True)
    ]
    xs = [t[0] for t in targets]
    assert max(xs) - min(xs) <= 1.5
    assert [t[1] for t in targets] == [10.0, 26.0, 42.0, 58.0]


def test_defensive_line_rises_with_line_height_and_ball() -> None:
    d = np.array([30.0, 30.0, 30.0, 30.0])
    assert defensive_line(d, 60.0, 0.9) > defensive_line(d, 60.0, 0.1)
    assert defensive_line(d, 80.0, 0.5) > defensive_line(d, 40.0, 0.5)
    assert defensive_line(d, 20.0, 0.9) <= 20.0 - 2.0  # never ahead of the ball
    assert defensive_line(d, 3.0, 0.5) >= 1.0


def test_offside_line_is_second_last_defender_or_ball() -> None:
    opponents = np.array([[101.0, 34.0], [80.0, 20.0], [78.0, 40.0], [60.0, 30.0]])
    assert offside_line(opponents, np.array([50.0, 30.0]), attacks_right=True) == 80.0
    assert offside_line(opponents, np.array([90.0, 30.0]), attacks_right=True) == 90.0
    left = np.array([105.0, 68.0]) - opponents
    assert offside_line(left, np.array([55.0, 38.0]), attacks_right=False) == pytest.approx(25.0)


def test_run_in_behind_waits_onside_then_goes() -> None:
    line = 80.0
    waiting, slow = role_target("run_in_behind", _ctx(offside_line=line))
    going, fast = role_target("run_in_behind", _ctx(offside_line=line, run_started=True))
    assert waiting[0] == pytest.approx(line - RUN_HOVER_M)
    assert going[0] > line + 10 and fast == 1.0 and slow < fast


def _striker_x_at_pass(release_early_s: float) -> float:
    """Runner waits onside, releases `release_early_s` before the pass, and is checked
    at the moment of the pass."""
    line = 80.0
    striker = Player(player_id="h-09", name="S", club_id="h", number=9, position="FW",
                     pace=0.6, skill=0.5, stamina=0.5)  # fmt: skip
    hover, _ = role_target("run_in_behind", _ctx(offside_line=line))
    state = PlayerState(pos=hover.copy(), vel=np.zeros(2), energy=1.0)
    pass_tick, release_tick = 30, 30 - round(release_early_s * 10)
    for k in range(pass_tick):
        started = k >= release_tick
        ctx = _ctx(pos=state.pos, offside_line=line, run_started=started)
        target, urgency = role_target("run_in_behind", ctx)
        state = step_player(state, target, urgency, striker)
    return float(state.pos[0])


@pytest.mark.parametrize(("early_s", "offside"), [(0.0, False), (0.2, False), (0.5, True)])
def test_early_release_leaves_the_runner_offside(early_s: float, offside: bool) -> None:
    x = _striker_x_at_pass(early_s)
    defenders = [(101.0, 34.0), (80.0, 20.0), (80.0, 48.0)]
    players = [PlayerPos(player_id="h-09", team_id="h", x=x, y=34.0, vx=0, vy=0)] + [
        PlayerPos(player_id=f"a-{i}", team_id="a", x=dx, y=dy, vx=0, vy=0)
        for i, (dx, dy) in enumerate(defenders)
    ]
    frame = TrackingFrame(match_id="m", frame=0, period=1, t=0.0, ball=(60.0, 34.0, 0.1),
                          players=players)  # fmt: skip
    assert (offside_players(frame, "h", attacks_right=True) == {"h-09"}) is offside


def test_timing_error_spread_scales() -> None:
    rng = np.random.default_rng(0)
    tight = [draw_timing_error(rng, scale=0.5) for _ in range(4000)]
    loose = [draw_timing_error(rng, scale=1.5) for _ in range(4000)]
    assert np.std(tight) < np.std(loose)
    assert abs(np.mean(loose)) < 0.05
