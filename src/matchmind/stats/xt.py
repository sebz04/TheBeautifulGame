"""Expected threat (xT, Singh 2019), trained only on our synthetic events.

The pitch is split into an `ny` x `nx` grid (default 12 x 16). For each cell z:
shoot probability s(z), move probability m(z) = 1 - s(z), goal probability g(z) per
shot, and the transition matrix T(z, z') of *completed* moves (failed moves count in
the denominator, so they lose value). xT solves xT = s*g + m * (T @ xT), by value
iteration from zero. Events must be in the attacking-right frame (`normalize_events`).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH, attacks_right, zone_index
from matchmind.schemas import Event, MatchData

MOVE_TYPES = frozenset({"pass", "carry"})  # kickoffs are restarts, not choices
DEFAULT_GRID_PATH = Path(__file__).resolve().parents[3] / "data" / "models" / "xt_grid.npy"


@dataclass(frozen=True)
class XTModel:
    """Per-cell probabilities (flattened row-major: index = row * nx + col)."""

    nx: int
    ny: int
    shoot: np.ndarray  # (n,)
    move: np.ndarray  # (n,)
    goal: np.ndarray  # (n,) goals per shot
    transition: np.ndarray  # (n, n) completed moves z -> z' / all moves from z


def _mirror(e: Event) -> Event:
    return e.model_copy(
        update={
            "x": PITCH_LENGTH - e.x,
            "y": PITCH_WIDTH - e.y,
            "end_x": None if e.end_x is None else PITCH_LENGTH - e.end_x,
            "end_y": None if e.end_y is None else PITCH_WIDTH - e.end_y,
        }
    )


def normalize_events(data: MatchData) -> list[Event]:
    """Copies of the match events, mirrored so the acting team always attacks right."""
    home = data.meta.home.club_id
    return [e if attacks_right(e.team_id == home, e.period) else _mirror(e) for e in data.events]


def _cell(x: float, y: float, nx: int, ny: int) -> int:
    col, row = zone_index(x, y, nx, ny)
    return row * nx + col


def transition_model(events: Iterable[Event], nx: int = 16, ny: int = 12) -> XTModel:
    n = nx * ny
    shots = np.zeros(n)
    goals = np.zeros(n)
    moves = np.zeros(n)
    completed = np.zeros((n, n))
    for e in events:
        if e.type == "shot":
            z = _cell(e.x, e.y, nx, ny)
            shots[z] += 1
            goals[z] += bool(e.outcome)
        elif e.type in MOVE_TYPES and e.end_x is not None and e.end_y is not None:
            z = _cell(e.x, e.y, nx, ny)
            moves[z] += 1
            if e.outcome:
                completed[z, _cell(e.end_x, e.end_y, nx, ny)] += 1
    actions = shots + moves
    with np.errstate(invalid="ignore", divide="ignore"):
        shoot = np.where(actions > 0, shots / actions, 0.0)
        move = np.where(actions > 0, moves / actions, 0.0)
        goal = np.where(shots > 0, goals / shots, 0.0)
        transition = np.where(moves[:, None] > 0, completed / moves[:, None], 0.0)
    return XTModel(nx, ny, shoot, move, goal, transition)


def solve_xt(model: XTModel, iters: int = 50) -> np.ndarray:
    """Value iteration from zero; returns the (ny, nx) grid."""
    reward = model.shoot * model.goal
    value = np.zeros_like(reward)
    for _ in range(iters):
        value = reward + model.move * (model.transition @ value)
    grid: np.ndarray = value.reshape(model.ny, model.nx)
    return grid


def train_xt(events: Iterable[Event], nx: int = 16, ny: int = 12, iters: int = 50) -> np.ndarray:
    """(ny, nx) xT grid from attacking-right events; row 0 is y near 0."""
    return solve_xt(transition_model(events, nx, ny), iters)


def load_xt(path: Path | None = None) -> np.ndarray:
    grid: np.ndarray = np.load(path or DEFAULT_GRID_PATH)
    return grid


def xt_value(grid: np.ndarray, x: float, y: float) -> float:
    """Value at an attacking-right point; points off the pitch use the nearest cell."""
    ny, nx = grid.shape
    col, row = zone_index(x, y, nx, ny)
    return float(grid[row, col])


def xt_added(grid: np.ndarray, event: Event, attacks_right: bool = True) -> float | None:
    """End minus start value for a completed pass or carry; None for anything else.

    `attacks_right` is the acting team's direction (see `engine.pitch.attacks_right`).
    """
    if event.type not in MOVE_TYPES or not event.outcome:
        return None
    if event.end_x is None or event.end_y is None:
        return None
    e = event if attacks_right else _mirror(event)
    assert e.end_x is not None and e.end_y is not None
    return xt_value(grid, e.end_x, e.end_y) - xt_value(grid, e.x, e.y)
