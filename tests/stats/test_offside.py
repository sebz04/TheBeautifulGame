import metrica_pitch_control as ref
import numpy as np
import pytest
from test_pitch_control import AWAY, HOME, KEEPERS, _frame, _random_frame, _reference_grid

from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH
from matchmind.schemas import TrackingFrame
from matchmind.stats.pitch_control import (
    grid_centres,
    offside_players,
    pitch_control_at,
    pitch_control_grid,
)

# Away defends the right-hand goal (keeper at x = 101); home attacks right.
DEFENCE = [(101.0, 34.0, 0, 0), (80.0, 20.0, 0, 0), (80.0, 48.0, 0, 0), (75.0, 34.0, 0, 0)]


def _with_attacker(x: float, ball_x: float = 60.0) -> TrackingFrame:
    return _frame([(4.0, 34.0, 0, 0), (x, 30.0, 0, 0)], DEFENCE, ball=(ball_x, 34.0))


@pytest.mark.parametrize(
    ("attacker_x", "ball_x", "offside"),
    [
        (85.0, 60.0, True),  # beyond the second-last defender (x = 80)
        (80.1, 60.0, False),  # level within the 0.2 m tolerance
        (45.0, 30.0, False),  # in his own half
        (85.0, 90.0, False),  # behind the ball
    ],
)
def test_offside_rule_cases(attacker_x: float, ball_x: float, offside: bool) -> None:
    frame = _with_attacker(attacker_x, ball_x)
    assert (offside_players(frame, HOME, attacks_right=True) == {"home-02"}) is offside
    assert "home-01" not in offside_players(frame, HOME, attacks_right=True)


def test_offside_rule_other_direction() -> None:
    players = [p.model_copy(update={"x": PITCH_LENGTH - p.x}) for p in _with_attacker(85.0).players]
    mirrored = TrackingFrame(match_id="m", frame=0, period=1, t=0.0,
                             ball=(PITCH_LENGTH - 60.0, 34.0, 0.1), players=players)  # fmt: skip
    assert offside_players(mirrored, HOME, attacks_right=False) == {"home-02"}
    # Read in the wrong direction, the striker (deep in that half) is not offside.
    assert "home-02" not in offside_players(mirrored, HOME, attacks_right=True)


def _reference_offside(frame: TrackingFrame) -> set[str]:
    params = ref.default_model_params()

    def row(team: str, name: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for p in frame.players:
            if p.team_id == team:
                num = p.player_id.split("-")[1]
                out.update({f"{name}_{num}_x": p.x - PITCH_LENGTH / 2,
                            f"{name}_{num}_y": p.y - PITCH_WIDTH / 2,
                            f"{name}_{num}_vx": p.vx, f"{name}_{num}_vy": p.vy})  # fmt: skip
        return out

    att = ref.initialise_players(row(HOME, "Home"), "Home", params, "01")
    dfn = ref.initialise_players(row(AWAY, "Away"), "Away", params, "01")
    ball = np.array([frame.ball[0] - PITCH_LENGTH / 2, frame.ball[1] - PITCH_WIDTH / 2])
    onside = {p.id for p in ref.check_offsides(att, dfn, ball, ("01", "01"))}
    return {f"home-{p.id}" for p in att} - {f"home-{i}" for i in onside}


@pytest.mark.parametrize("seed", [11, 12, 13, 14, 15])
def test_offside_matches_reference(seed: int) -> None:
    frame = _random_frame(seed)
    assert offside_players(frame, HOME, attacks_right=True) == _reference_offside(frame)


def test_offside_striker_gets_no_control() -> None:
    frame = _with_attacker(88.0, ball_x=55.0)
    target = np.array([[89.0, 30.0]])
    before = pitch_control_at(frame, HOME, target, goalkeepers=KEEPERS)
    after = pitch_control_at(frame, HOME, target, goalkeepers=KEEPERS, attacks_right=True)
    assert before[0] > 0.5 > after[0]


def test_some_parity_frame_has_an_offside() -> None:
    assert any(offside_players(_random_frame(s), HOME, attacks_right=True) for s in range(11, 16))


@pytest.mark.parametrize("seed", [11, 13])
def test_parity_with_reference_offsides(seed: int) -> None:
    frame = _random_frame(seed)
    xs, ys = grid_centres(32, 21)
    keep = [p for p in frame.players if p.player_id not in _reference_offside(frame)]
    expected = _reference_grid(frame.model_copy(update={"players": keep}), HOME, xs, ys,
                               ref.default_model_params())  # fmt: skip
    got = pitch_control_grid(frame, HOME, goalkeepers=KEEPERS, attacks_right=True)
    assert np.max(np.abs(got - expected)) <= 0.02
