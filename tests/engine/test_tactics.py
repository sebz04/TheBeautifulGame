import numpy as np
import pytest

from matchmind.engine.lineup import FORMATION_LINES
from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH
from matchmind.engine.tactics import (
    PHASES,
    formation_shape,
    pressing_trigger,
    runs_in_behind_rate,
    shape_lines,
)
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles
from matchmind.schemas import Event, PlayerPos, TrackingFrame


@pytest.mark.parametrize("formation", list(FORMATION_LINES))
@pytest.mark.parametrize("n", [11, 10, 9])
def test_shapes_work_for_11_10_and_9_players(formation: str, n: int) -> None:
    for phase in PHASES:
        shape = formation_shape(formation, phase, n)
        assert shape.shape == (n, 2)
        assert np.all(shape[:, 0] > 0) and np.all(shape[:, 0] < PITCH_LENGTH)
        assert np.all(shape[:, 1] > 0) and np.all(shape[:, 1] < PITCH_WIDTH)
        assert shape[0, 0] == shape[:, 0].min()  # the keeper is the deepest
        gaps = np.hypot(*(shape[:, None] - shape[None, :]).transpose(2, 0, 1))
        assert gaps[~np.eye(n, dtype=bool)].min() > 3.0  # nobody stacked on a teammate
    lines = shape_lines(formation, n)
    assert lines[0] == "GK" and len(lines) == n
    assert lines.count("DF") == FORMATION_LINES[formation][0]  # forwards go first


def test_ten_men_lose_the_most_advanced_slot() -> None:
    full, ten = formation_shape("4-4-2", "mid_block", 11), formation_shape("4-4-2", "mid_block", 10)
    assert ten[:, 0].max() <= full[:, 0].max()
    assert shape_lines("4-4-2", 10).count("FW") == 1
    assert shape_lines("4-3-3", 9).count("FW") == 1


def test_phase_depths_are_ordered() -> None:
    def depth(phase: str) -> float:
        return float(formation_shape("4-3-3", phase, 11)[1:, 0].mean())  # type: ignore[arg-type]

    assert depth("low_block") < depth("mid_block") < depth("build_up") < depth("high_press")
    assert depth("set_piece") < depth("low_block")
    assert depth("build_up") < depth("counter")


def test_blocks_are_narrower_than_build_up() -> None:
    def width(phase: str) -> float:
        s = formation_shape("4-3-3", phase, 11)  # type: ignore[arg-type]
        return float(np.ptp(s[1:, 1]))

    assert width("low_block") < width("mid_block") < width("build_up")


# ---- pressing triggers ----------------------------------------------------------------
# The pressing team is "a"; it attacks left (toward x = 0), so "h" attacks right.


def _frame(carrier_vx: float = 2.0) -> TrackingFrame:
    players = [
        PlayerPos(player_id="h-1", team_id="h", x=40.0, y=34.0, vx=carrier_vx, vy=0.0),
        PlayerPos(player_id="a-1", team_id="a", x=45.0, y=34.0, vx=0.0, vy=0.0),
    ]
    return TrackingFrame(match_id="m", frame=0, period=1, t=10.0, ball=(40.3, 34.0, 0.11),
                         players=players)  # fmt: skip


def _pass(x: float, end_x: float, **extras: object) -> Event:
    return Event(event_id="m-e00001", match_id="m", period=1, t=8.0, type="pass", team_id="h",
                 player_id="h-2", x=x, y=34.0, end_x=end_x, end_y=34.0, outcome=True,
                 receiver_id="h-1", ball_speed_ms=12.0, extras=extras)  # fmt: skip


def test_pressing_trigger_fires_on_back_pass() -> None:
    assert pressing_trigger(_pass(55.0, 40.0), _frame(), "a", attacks_right=False)


def test_pressing_trigger_fires_on_poor_touch() -> None:
    assert pressing_trigger(_pass(30.0, 40.0, heavy_touch=True), _frame(), "a", False)


def test_pressing_trigger_fires_when_receiver_faces_own_goal() -> None:
    assert pressing_trigger(_pass(30.0, 40.0), _frame(carrier_vx=-3.0), "a", False)


def test_back_pass_in_midfield_is_not_a_trigger() -> None:
    # h attacks right: 80 -> 70 is backwards but stays in the opponent's half.
    assert not pressing_trigger(_pass(80.0, 70.0), _frame(), "a", attacks_right=False)


def test_no_trigger_on_a_clean_forward_pass() -> None:
    assert not pressing_trigger(_pass(30.0, 40.0), _frame(), "a", False)
    assert not pressing_trigger(None, _frame(), "a", False)


def test_own_team_pass_is_not_a_trigger() -> None:
    back = _pass(55.0, 40.0).model_copy(update={"team_id": "a"})
    assert not pressing_trigger(back, _frame(), "a", False)


# ---- runs in behind ----------------------------------------------------------------------


def _club(**tactics: float):  # type: ignore[no-untyped-def]
    club = next(iter(build_profiles(build_league(), seed=2026).clubs.values()))
    identity = club.tactical_identity.model_copy(update=tactics)
    return club.model_copy(update={"tactical_identity": identity})


def test_runs_in_behind_rise_with_tactics_role_pace_and_line() -> None:
    base = runs_in_behind_rate(_club(directness=0.5, tempo=0.5), "poacher", 0.5, pace=0.5)
    assert runs_in_behind_rate(_club(directness=0.9, tempo=0.5), "poacher", 0.5, 0.5) > base
    assert runs_in_behind_rate(_club(directness=0.5, tempo=0.9), "poacher", 0.5, 0.5) > base
    assert runs_in_behind_rate(_club(directness=0.5, tempo=0.5), "target_man", 0.5, 0.5) < base
    assert runs_in_behind_rate(_club(directness=0.5, tempo=0.5), "poacher", 0.9, 0.5) > base
    assert runs_in_behind_rate(_club(directness=0.5, tempo=0.5), "poacher", 0.5, 0.9) > base


def test_runs_in_behind_are_tactics_not_capped() -> None:
    low = runs_in_behind_rate(_club(directness=0.1, tempo=0.1), "target_man", 0.1, 0.1)
    high = runs_in_behind_rate(_club(directness=0.9, tempo=0.9), "poacher", 0.9, 0.9)
    assert high > 3 * low  # far beyond the 6% subtle cap
