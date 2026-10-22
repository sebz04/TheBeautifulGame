"""Ball flight: ground passes roll, lofted balls and shots fly, then bounce and roll.

The ball is integrated in 0.02 s sub-steps and sampled at the 10 Hz frame rate.
Quadratic air drag (`DRAG_K`, about a real ball's value) acts in the air and on the
ground; a rolling ball also loses `ROLL_DECEL` m/s^2 to the grass. A lofted ball's
launch angle is solved so its first bounce lands on the target. A trajectory stops at
the first sample after the ball crosses a touchline or goal line (`out_of_play`), and
the last touch decides the restart (`restart_for`).
"""

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH

Kind = Literal["ground", "lofted", "shot"]
Deflection = Literal["block", "parry"]
Restart = Literal["throw_in", "goal_kick", "corner"]

DT = 0.1
SUB_STEPS = 5
G = 9.81
BALL_RADIUS_M = 0.11
DRAG_K = 0.010  # 1/m: dv/dt = -k |v| v (0.5 * rho * Cd * A / m for a size-5 ball)
ROLL_DECEL = 0.7  # m/s^2, rolling resistance on grass
BOUNCE_RESTITUTION = 0.5  # vertical speed kept at a bounce
BOUNCE_GRIP = 0.75  # horizontal speed kept at a bounce
SETTLE_VZ = 1.0  # m/s: below this the ball stops bouncing and rolls
STOP_SPEED = 0.3  # m/s: the ball has stopped
MAX_FLIGHT_S = 12.0
GOAL_HALF_WIDTH = 3.66
GOAL_HEIGHT = 2.44
SHOT_LOFT_DEG = 5.0
LOFT_RANGE_DEG = (8.0, 45.0)

# Deflections: (speed kept lo, hi), spread of the new direction (degrees, SD).
DEFLECT_KEEP: dict[str, tuple[float, float]] = {"block": (0.2, 0.6), "parry": (0.25, 0.55)}
DEFLECT_SPREAD_DEG: dict[str, float] = {"block": 55.0, "parry": 70.0}

GROUND_SPEED_MS = (10.0, 22.0)
LOFTED_SPEED_MS = (14.0, 30.0)
SHOT_SPEED_MS = (18.0, 32.0)
_SPEED_RANGE: dict[str, tuple[float, float]] = {
    "ground": GROUND_SPEED_MS,
    "lofted": LOFTED_SPEED_MS,
    "shot": SHOT_SPEED_MS,
}


@dataclass(frozen=True)
class Trajectory:
    t: np.ndarray  # (n,) seconds since the kick, 0.1 s apart
    xyz: np.ndarray  # (n, 3)
    duration: float  # time to travel the distance to `end`, or to stop/leave play first
    reaches_end: bool
    out: tuple[float, np.ndarray] | None  # (time, point on the line) if it leaves play

    def positions_at(self, t: float) -> np.ndarray:
        """(x, y, z) at time t; before 0 the start, after the last sample the last one."""
        u = min(max(t / DT, 0.0), len(self.t) - 1.0)
        i = min(int(u), len(self.t) - 2) if len(self.t) > 1 else 0
        if len(self.t) == 1:
            first: np.ndarray = self.xyz[0].copy()
            return first
        w = u - i
        point: np.ndarray = (1.0 - w) * self.xyz[i] + w * self.xyz[i + 1]
        return point

    def out_of_play(self) -> tuple[float, np.ndarray] | None:
        return self.out


def _crossing(
    prev: tuple[float, float, float], cur: tuple[float, float, float]
) -> tuple[float, np.ndarray] | None:
    """Fraction of the step at which the ball left the pitch, and the point on the line."""
    best: tuple[float, np.ndarray] | None = None
    for axis, limit in ((0, 0.0), (0, PITCH_LENGTH), (1, 0.0), (1, PITCH_WIDTH)):
        a, b = prev[axis], cur[axis]
        inside_a = a >= 0.0 if limit == 0.0 else a <= limit
        inside_b = b >= 0.0 if limit == 0.0 else b <= limit
        if inside_a and not inside_b:
            w = (limit - a) / (b - a)
            if best is None or w < best[0]:
                p = np.array([prev[i] + w * (cur[i] - prev[i]) for i in range(3)])
                p[axis] = limit
                best = (w, p)
    return best


def _simulate(
    start: tuple[float, float],
    direction: tuple[float, float],
    speed: float,
    loft_deg: float,
    distance: float,
    stop_at_out: bool = True,
) -> Trajectory:
    h = DT / SUB_STEPS
    ux, uy = direction
    x, y, z = start[0], start[1], BALL_RADIUS_M
    horiz = speed * math.cos(math.radians(loft_deg))
    vx, vy, vz = horiz * ux, horiz * uy, speed * math.sin(math.radians(loft_deg))
    ts, pts = [0.0], [(x, y, z)]
    duration: float | None = None
    out: tuple[float, np.ndarray] | None = None
    travelled = 0.0
    t = 0.0
    n_ticks = round(MAX_FLIGHT_S / DT)
    stopped = False
    for k in range(1, n_ticks + 1):
        for _ in range(SUB_STEPS):
            prev = (x, y, z)
            v = math.sqrt(vx * vx + vy * vy + vz * vz)
            airborne = z > BALL_RADIUS_M + 1e-9 or vz > 0.0
            if airborne:
                vx -= DRAG_K * v * vx * h
                vy -= DRAG_K * v * vy * h
                vz -= (G + DRAG_K * v * vz) * h
            else:
                vh = math.hypot(vx, vy)
                if vh < STOP_SPEED:
                    vx = vy = 0.0
                    stopped = True
                else:
                    scale = max(vh - (ROLL_DECEL + DRAG_K * vh * vh) * h, 0.0) / vh
                    vx, vy = vx * scale, vy * scale
            x, y, z = x + vx * h, y + vy * h, z + vz * h
            if z < BALL_RADIUS_M:
                z = BALL_RADIUS_M
                if vz < -SETTLE_VZ:
                    vz = -BOUNCE_RESTITUTION * vz
                    vx, vy = vx * BOUNCE_GRIP, vy * BOUNCE_GRIP
                else:
                    vz = 0.0
            step = math.hypot(x - prev[0], y - prev[1])
            if duration is None and travelled + step >= distance and step > 0.0:
                duration = t + h * (distance - travelled) / step
            travelled += step
            if out is None:
                cross = _crossing(prev, (x, y, z))
                if cross is not None:
                    out = (t + cross[0] * h, cross[1])
            t += h
            if stopped:
                break
        ts.append(k * DT)
        pts.append((x, y, z))
        if stopped or (out is not None and stop_at_out):
            break
    reaches = duration is not None and (out is None or duration <= out[0] + 1e-6)
    if not reaches:
        duration = out[0] if out is not None else ts[-1]
    assert duration is not None
    return Trajectory(np.array(ts), np.array(pts), duration, reaches, out)


def _landing_distance(speed: float, loft_deg: float) -> float:
    """Horizontal distance to the first bounce (drag included)."""
    h = DT / SUB_STEPS
    horiz = speed * math.cos(math.radians(loft_deg))
    vx, vz, x, z = horiz, speed * math.sin(math.radians(loft_deg)), 0.0, BALL_RADIUS_M
    while True:
        v = math.hypot(vx, vz)
        vx -= DRAG_K * v * vx * h
        vz -= (G + DRAG_K * v * vz) * h
        x, z = x + vx * h, z + vz * h
        if z <= BALL_RADIUS_M:
            return x


def loft_for(speed: float, distance: float) -> float:
    """Low launch angle (degrees) whose first bounce lands `distance` away; the largest
    angle in `LOFT_RANGE_DEG` when even that falls short."""
    lo, hi = LOFT_RANGE_DEG
    if _landing_distance(speed, hi) <= distance:
        return hi
    if _landing_distance(speed, lo) >= distance:
        return lo
    for _ in range(20):
        mid = 0.5 * (lo + hi)
        if _landing_distance(speed, mid) < distance:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def flight(
    start: tuple[float, float] | np.ndarray,
    end: tuple[float, float] | np.ndarray,
    kind: Kind,
    speed_ms: float,
    loft_deg: float | None = None,
) -> Trajectory:
    """The ball kicked from `start` toward `end` at `speed_ms`.

    `duration` is when the ball has travelled the distance to `end` (a lofted ball lands
    there on its first bounce); a ball that stops or leaves play first never gets there
    (`reaches_end` False). Shots fly at `loft_deg` (default `SHOT_LOFT_DEG`).
    """
    sx, sy = float(start[0]), float(start[1])
    dx, dy = float(end[0]) - sx, float(end[1]) - sy
    distance = math.hypot(dx, dy)
    if distance < 1e-9:
        point = np.array([[sx, sy, BALL_RADIUS_M]])
        return Trajectory(np.zeros(1), point, 0.0, True, None)
    if loft_deg is None:
        if kind == "ground":
            loft_deg = 0.0
        elif kind == "shot":
            loft_deg = SHOT_LOFT_DEG
        else:
            loft_deg = loft_for(speed_ms, distance)
    return _simulate((sx, sy), (dx / distance, dy / distance), speed_ms, loft_deg, distance)


def draw_speed(rng: np.random.Generator, kind: Kind, distance: float, skill: float) -> float:
    """Kick speed for a ball meant to travel `distance` m, within the kind's range.

    Longer balls are struck harder; better players strike shots harder.
    """
    lo, hi = _SPEED_RANGE[kind]
    if kind == "ground":
        base = 9.0 + 0.3 * distance
    elif kind == "lofted":
        base = 14.0 + 0.28 * distance
    else:
        base = 21.0 + 6.0 * skill
    return float(np.clip(base + rng.normal(0.0, 1.5), lo, hi))


def deflect(
    rng: np.random.Generator, incoming: tuple[float, float], speed: float, kind: Deflection
) -> tuple[np.ndarray, float]:
    """New unit direction and speed after a blocked shot or a parried save.

    The ball keeps part of its speed and mostly carries on in its direction, turned by a
    wide random angle: often sideways, sometimes behind for a corner.
    """
    lo, hi = DEFLECT_KEEP[kind]
    angle = math.atan2(incoming[1], incoming[0])
    angle += math.radians(float(rng.normal(0.0, DEFLECT_SPREAD_DEG[kind])))
    direction = np.array([math.cos(angle), math.sin(angle)])
    return direction, speed * float(rng.uniform(lo, hi))


def in_goal_mouth(point: np.ndarray) -> bool:
    """On a goal line, between the posts and under the bar."""
    on_line = point[0] <= 1e-6 or point[0] >= PITCH_LENGTH - 1e-6
    between = abs(float(point[1]) - PITCH_WIDTH / 2) <= GOAL_HALF_WIDTH
    return bool(on_line and between and float(point[2]) <= GOAL_HEIGHT)


def restart_for(point: tuple[float, float] | np.ndarray, last_touch_attacks_right: bool) -> Restart:
    """How play restarts after the ball left at `point` (not a goal).

    Over a touchline: a throw-in. Over a goal line: a goal kick if the last touch was by
    the team attacking that goal, a corner if it was by the team defending it.
    """
    x = float(point[0])
    if 1e-6 < x < PITCH_LENGTH - 1e-6:
        return "throw_in"
    attacking_this_line = (x >= PITCH_LENGTH / 2) == last_touch_attacks_right
    return "goal_kick" if attacking_this_line else "corner"
