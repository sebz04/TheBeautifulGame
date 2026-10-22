import numpy as np
import pytest

from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH
from matchmind.schemas import Club, Event, EventType, MatchData, MatchMeta
from matchmind.stats.xt import (
    load_xt,
    normalize_events,
    train_xt,
    transition_model,
    xt_added,
    xt_value,
)

MID = "r01-h-v-a"


def _ev(n: int, type_: EventType, x: float, y: float, end: tuple[float, float] | None = None,
        outcome: bool | None = True, team: str = "h", period: int = 1) -> Event:  # fmt: skip
    return Event(
        event_id=f"{MID}-e{n:05d}", match_id=MID, period=period, t=float(n), type=type_,  # type: ignore[arg-type]
        team_id=team, player_id=f"{team}-p", x=x, y=y,
        end_x=None if end is None else end[0], end_y=None if end is None else end[1],
        outcome=outcome, receiver_id=None, ball_speed_ms=None,
    )  # fmt: skip


def test_hand_worked_two_cell_example() -> None:
    # Two cells (nx=2, ny=1): left L (x < 52.5) and right R.
    # R: 1 shot (scored), 1 completed move R->R, 1 failed move -> s=1/3, m=2/3, g=1, T(R,R)=1/2
    #    xT_R = 1/3 + 2/3 * 1/2 * xT_R  =>  xT_R = 0.5
    # L: 1 completed move L->R, 1 failed move -> s=0, m=1, T(L,R)=1/2  =>  xT_L = 0.25
    events = [
        _ev(0, "shot", 90, 34, outcome=True),
        _ev(1, "pass", 80, 30, end=(95, 40)),
        _ev(2, "pass", 80, 30, end=(95, 40), outcome=False),
        _ev(3, "carry", 20, 34, end=(70, 34)),
        _ev(4, "pass", 20, 34, end=(40, 34), outcome=False),
    ]
    grid = train_xt(events, nx=2, ny=1, iters=200)
    assert grid.shape == (1, 2)
    assert grid[0, 0] == pytest.approx(0.25, abs=1e-6)
    assert grid[0, 1] == pytest.approx(0.5, abs=1e-6)


def test_value_iteration_matches_linear_solve() -> None:
    rng = np.random.default_rng(0)
    events = []
    for n in range(4000):
        x, y = rng.uniform(0, PITCH_LENGTH), rng.uniform(0, PITCH_WIDTH)
        if x > 80 and rng.random() < 0.15:
            events.append(_ev(n, "shot", x, y, outcome=bool(rng.random() < (x - 70) / 100)))
        else:
            end = (min(x + rng.normal(8, 12), 105.0), float(np.clip(y + rng.normal(0, 10), 0, 68)))
            events.append(_ev(n, "pass", x, y, end=(max(end[0], 0.0), end[1]),
                              outcome=bool(rng.random() < 0.8)))  # fmt: skip
    model = transition_model(events, nx=16, ny=12)
    n_cells = 16 * 12
    a = np.eye(n_cells) - model.move[:, None] * model.transition
    exact = np.linalg.solve(a, model.shoot * model.goal).reshape(12, 16)
    assert np.allclose(train_xt(events, iters=500), exact, atol=1e-9)
    assert np.allclose(train_xt(events), exact, atol=1e-3)  # default iterations


def test_normalize_mirrors_teams_attacking_left() -> None:
    meta = MatchMeta.model_construct(
        match_id=MID,
        home=Club(club_id="h", name="H", short="HHH", primary_color="#000000",
                  secondary_color="#FFFFFF", formation="4-3-3"),
        away=Club(club_id="a", name="A", short="AAA", primary_color="#000000",
                  secondary_color="#FFFFFF", formation="4-3-3"),
    )  # fmt: skip
    events = [
        _ev(0, "pass", 10, 20, end=(30, 25)),  # home, period 1: attacks right, unchanged
        _ev(1, "pass", 10, 20, end=(30, 25), team="a"),  # away, period 1: mirrored
        _ev(2, "shot", 100, 30, period=2),  # home, period 2: mirrored
    ]
    data = MatchData.model_construct(meta=meta, events=events, frames=[])
    out = normalize_events(data)
    assert (out[0].x, out[0].y, out[0].end_x, out[0].end_y) == (10, 20, 30, 25)
    assert (out[1].x, out[1].y, out[1].end_x, out[1].end_y) == (95, 48, 75, 43)
    assert (out[2].x, out[2].y) == (5, 38)
    assert out[1].event_id == events[1].event_id


def test_trained_grid_bounded_and_monotone_toward_goal() -> None:
    grid = load_xt()
    assert grid.shape == (12, 16)
    assert np.all((grid >= 0) & (grid <= 1))
    assert grid[:, -1].mean() > grid[:, 0].mean()
    assert grid[:, -4:].mean() > grid[:, 4:8].mean() > 0


def test_edge_lookup() -> None:
    grid = load_xt()
    for x, y in [(105.0, 68.0), (0.0, 0.0), (110.0, -3.0)]:
        assert np.isfinite(xt_value(grid, x, y))
    assert xt_value(grid, 105.0, 34.0) == grid[6, 15]


def test_xt_added() -> None:
    grid = load_xt()
    ok = _ev(0, "pass", 30, 34, end=(90, 34))
    assert xt_added(grid, ok) == pytest.approx(xt_value(grid, 90, 34) - xt_value(grid, 30, 34))
    assert xt_added(grid, ok) > 0
    # The same pass by a team attacking left goes backwards.
    assert xt_added(grid, ok, attacks_right=False) < 0


def test_xt_added_none_for_failed_pass_and_other_events() -> None:
    grid = load_xt()
    assert xt_added(grid, _ev(0, "pass", 30, 34, end=(90, 34), outcome=False)) is None
    assert xt_added(grid, _ev(1, "shot", 90, 34)) is None
    assert xt_added(grid, _ev(2, "carry", 30, 34, end=None)) is None
