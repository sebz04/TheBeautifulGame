import time

import metrica_pitch_control as ref
import numpy as np
import pytest

from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH
from matchmind.schemas import PlayerPos, TrackingFrame
from matchmind.stats.pitch_control import PCParams, pitch_control_at, pitch_control_grid

HOME, AWAY = "home", "away"
KEEPERS = frozenset({"home-01", "away-01"})


def _frame(
    home: list[tuple[float, float, float, float]],
    away: list[tuple[float, float, float, float]],
    ball: tuple[float, float] = (52.5, 34.0),
) -> TrackingFrame:
    players = [
        PlayerPos(player_id=f"{team}-{i + 1:02d}", team_id=team, x=x, y=y, vx=vx, vy=vy)
        for team, rows in ((HOME, home), (AWAY, away))
        for i, (x, y, vx, vy) in enumerate(rows)
    ]
    return TrackingFrame(match_id="m", frame=0, period=1, t=0.0, ball=(*ball, 0.1),
                         players=players)  # fmt: skip


def _random_frame(seed: int, n_home: int = 11) -> TrackingFrame:
    rng = np.random.default_rng(seed)

    def side(n: int, keeper_x: float) -> list[tuple[float, float, float, float]]:
        rows = [(keeper_x, 34.0 + rng.normal(0, 2), 0.0, 0.0)]
        for _ in range(n - 1):
            rows.append((float(rng.uniform(15, 90)), float(rng.uniform(3, 65)),
                         float(rng.normal(0, 2.5)), float(rng.normal(0, 2.5))))  # fmt: skip
        return rows

    ball = (float(rng.uniform(20, 85)), float(rng.uniform(5, 63)))
    return _frame(side(n_home, 4.0), side(11, 101.0), ball)


def _mirror(frame: TrackingFrame) -> TrackingFrame:
    players = [
        p.model_copy(
            update={"x": PITCH_LENGTH - p.x, "y": PITCH_WIDTH - p.y, "vx": -p.vx, "vy": -p.vy}
        )  # fmt: skip
        for p in frame.players
    ]
    bx, by, bz = frame.ball
    return frame.model_copy(
        update={"players": players, "ball": (PITCH_LENGTH - bx, PITCH_WIDTH - by, bz)}
    )


def test_mirror_symmetry() -> None:
    frame = _random_frame(1)
    grid = pitch_control_grid(frame, HOME, goalkeepers=KEEPERS)
    mirrored = pitch_control_grid(_mirror(frame), HOME, goalkeepers=KEEPERS)
    assert np.allclose(mirrored, grid[::-1, ::-1], atol=1e-6)


def test_teams_sum_to_one_within_convergence() -> None:
    frame = _random_frame(2)
    # Without the keeper bonus (which only the defending keeper gets, so it changes with
    # the attacking team) the roles are symmetric. Two separate runs each stop within the
    # convergence tolerance, so the complement holds within twice the tolerance.
    home = pitch_control_grid(frame, HOME)
    away = pitch_control_grid(frame, AWAY)
    assert np.all(np.abs(home + away - 1.0) <= 2 * PCParams().model_converge_tol)


def test_attacker_alone() -> None:
    frame = _frame([(4.0, 34.0, 0, 0), (60.0, 34.0, 0, 0)], [(101.0, 34.0, 0, 0)],
                   ball=(60.0, 34.0))  # fmt: skip
    value = pitch_control_at(frame, HOME, np.array([[61.0, 34.0]]), goalkeepers=KEEPERS)
    assert value[0] > 0.95


def test_ten_vs_eleven() -> None:
    grid = pitch_control_grid(_random_frame(3, n_home=10), HOME, goalkeepers=KEEPERS)
    assert grid.shape == (21, 32)
    assert np.all(np.isfinite(grid)) and grid.min() >= 0 and grid.max() <= 1


def test_edge_targets() -> None:
    targets = np.array([[105.0, 68.0], [0.0, 34.0], [0.0, 0.0]])
    values = pitch_control_at(_random_frame(4), HOME, targets, goalkeepers=KEEPERS)
    assert np.all(np.isfinite(values)) and np.all((values >= 0) & (values <= 1))


def _reference_grid(frame: TrackingFrame, attacking: str, xs: np.ndarray, ys: np.ndarray,
                    params: dict[str, float]) -> np.ndarray:  # fmt: skip
    """Run the vendored Friends of Tracking code (centred coordinates, no offsides)."""

    def row(team: str, name: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for p in frame.players:
            if p.team_id != team:
                continue
            num = p.player_id.split("-")[1]
            out[f"{name}_{num}_x"] = p.x - PITCH_LENGTH / 2
            out[f"{name}_{num}_y"] = p.y - PITCH_WIDTH / 2
            out[f"{name}_{num}_vx"] = p.vx
            out[f"{name}_{num}_vy"] = p.vy
        return out

    other = AWAY if attacking == HOME else HOME
    att = ref.initialise_players(row(attacking, "Home"), "Home", params, "01")
    dfn = ref.initialise_players(row(other, "Away"), "Away", params, "01")
    ball = np.array([frame.ball[0] - PITCH_LENGTH / 2, frame.ball[1] - PITCH_WIDTH / 2])
    out = np.zeros((len(ys), len(xs)))
    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            target = np.array([x - PITCH_LENGTH / 2, y - PITCH_WIDTH / 2])
            out[i, j] = ref.calculate_pitch_control_at_target(target, att, dfn, ball, params)[0]
    return out


@pytest.mark.parametrize("seed", [11, 12, 13, 14, 15])
def test_parity_with_reference(seed: int) -> None:
    frame = _random_frame(seed)
    nx, ny = 32, 21
    xs = (np.arange(nx) + 0.5) * PITCH_LENGTH / nx
    ys = (np.arange(ny) + 0.5) * PITCH_WIDTH / ny
    expected = _reference_grid(frame, HOME, xs, ys, ref.default_model_params())
    got = pitch_control_grid(frame, HOME, nx=nx, ny=ny, goalkeepers=KEEPERS)
    assert np.max(np.abs(got - expected)) <= 0.02


def test_bench_grid_under_50ms() -> None:
    frame = _random_frame(21)
    pitch_control_grid(frame, HOME, goalkeepers=KEEPERS)  # warm-up
    timings = []
    for _ in range(5):
        start = time.perf_counter()
        pitch_control_grid(frame, HOME, goalkeepers=KEEPERS)
        timings.append(time.perf_counter() - start)
    assert min(timings) < 0.05, f"best of 5: {min(timings) * 1000:.1f} ms"
