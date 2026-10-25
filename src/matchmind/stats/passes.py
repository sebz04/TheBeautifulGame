"""Pass quality: distance, completion, difficulty, and xT added; player pass accuracy.

`difficulty = sigmoid(1.2 · distance/40 + 0.8 · defenders within 3 m of the lane
+ 1.5 · (1 − pitch control at the end) + 0.4 · lofted − 1.6)`, with fixed weights, so the
same pass always gets the same number. Pitch control is offside-filtered (Task 6.1) and
measured on the frame at the pass. Positions outside the pitch are clamped to its edge.
"""

import math
from collections.abc import Collection, Iterable

import numpy as np
from pydantic import BaseModel

from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH
from matchmind.schemas import Event, TrackingFrame
from matchmind.stats.pitch_control import pitch_control_at
from matchmind.stats.xt import xt_added

WEIGHTS = (1.2, 0.8, 1.5, 0.4)  # distance/40, lane defenders, 1 - pc at the end, lofted
BIAS = -1.6
LANE_M = 3.0
LOFTED_M = 30.0  # without an `extras.lofted` flag, passes this long count as lofted


class PassQuality(BaseModel):
    distance_m: float
    completed: bool
    difficulty: float  # [0, 1]
    xt_added: float | None  # completed passes only


def _lane_defenders(frame: TrackingFrame, team_id: str, start: np.ndarray, end: np.ndarray) -> int:
    seg = end - start
    n2 = float(seg @ seg)
    count = 0
    for p in frame.players:
        if p.team_id == team_id:
            continue
        rel = np.array([p.x, p.y]) - start
        u = min(max(float(rel @ seg) / n2, 0.0), 1.0) if n2 > 1e-12 else 0.0
        if float(np.hypot(*(rel - u * seg))) <= LANE_M:
            count += 1
    return count


def pass_quality(
    event: Event,
    frame: TrackingFrame,
    xt_grid: np.ndarray,
    attacks_right: bool,
    goalkeepers: Collection[str] = frozenset(),
) -> PassQuality:
    """Quality of a pass with an end point, on the frame at the moment it was played."""
    if event.end_x is None or event.end_y is None:
        raise ValueError(f"pass {event.event_id} has no end point")
    start = np.array([event.x, event.y])
    end = np.array([min(max(event.end_x, 0.0), PITCH_LENGTH),
                    min(max(event.end_y, 0.0), PITCH_WIDTH)])  # fmt: skip
    distance = float(np.hypot(*(end - start)))
    at_kick = frame.model_copy(update={"ball": (event.x, event.y, frame.ball[2])})
    pcs = pitch_control_at(at_kick, event.team_id, end.reshape(1, 2),
                           goalkeepers=goalkeepers, attacks_right=attacks_right)  # fmt: skip
    pc = float(pcs[0])
    lofted = bool(event.extras.get("lofted", distance >= LOFTED_M))
    features = (distance / 40.0, _lane_defenders(frame, event.team_id, start, end), 1.0 - pc,
                float(lofted))  # fmt: skip
    z = BIAS + sum(w * f for w, f in zip(WEIGHTS, features, strict=True))
    completed = bool(event.outcome)
    return PassQuality(
        distance_m=round(distance, 2),
        completed=completed,
        difficulty=1.0 / (1.0 + math.exp(-z)),
        xt_added=xt_added(xt_grid, event, attacks_right) if completed else None,
    )


def player_accuracy(events: Iterable[Event], player_id: str, t_to: tuple[int, float]) -> float:
    """Share of the player's passes completed up to (period, t), inclusive; NaN if none."""
    passes = [e for e in events if e.type == "pass" and e.player_id == player_id
              and (e.period, e.t) <= t_to]  # fmt: skip
    if not passes:
        return math.nan
    return sum(bool(e.outcome) for e in passes) / len(passes)
