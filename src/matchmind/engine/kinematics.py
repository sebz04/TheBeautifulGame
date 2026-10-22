"""Level-2 player kinematics: seek-with-arrival steering under speed, acceleration, and
deceleration caps, plus an energy store that drains with speed squared.

Top speed is `v_max(pace)` scaled by energy (`0.85 + 0.15 * energy`). `urgency` in [0, 1]
sets the cruising share of top speed (a walk-jog at 0, a sprint at 1). Speeding up is
capped by `A_MAX`, slowing down by `DECEL_MAX`; the arrival speed lets a player stop on
the target.
"""

import math
from dataclasses import dataclass

import numpy as np

from matchmind.schemas import Player

DT = 0.1
V_MAX_BASE = 8.0  # m/s at pace 0
V_MAX_PACE = 2.0  # + m/s at pace 1 (so 8-10 m/s; about 9 for an average player)
A_MAX = 3.5  # m/s^2, speeding up
DECEL_MAX = 5.0  # m/s^2, slowing down
MIN_CRUISE_SHARE = 0.25  # share of top speed at urgency 0
ARRIVAL_SLACK = 0.8  # brake earlier than the physical limit
DRAIN_K = 8.0e-5  # energy per (m/s)^2 per second, at stamina 0.5
RECOVERY_RATE = 0.002  # per second, toward 1, while slower than RECOVERY_SPEED
RECOVERY_SPEED = 2.0  # m/s


@dataclass(frozen=True)
class PlayerState:
    pos: np.ndarray  # (2,)
    vel: np.ndarray  # (2,)
    energy: float  # [0, 1]


def v_max(pace: float) -> float:
    return V_MAX_BASE + V_MAX_PACE * pace


def max_speed(player: Player, energy: float) -> float:
    """Top speed right now: fatigue takes up to 15% off."""
    return v_max(player.pace) * (0.85 + 0.15 * min(max(energy, 0.0), 1.0))


def _drain_factor(stamina: float) -> float:
    return 1.3 - 0.6 * stamina  # stamina 0.5 -> 1.0


def step_player(
    state: PlayerState, target: np.ndarray, urgency: float, attrs: Player, dt: float = DT
) -> PlayerState:
    top = max_speed(attrs, state.energy)
    to_target = np.asarray(target, dtype=float) - state.pos
    dist = float(np.hypot(*to_target))
    cruise = top * (MIN_CRUISE_SHARE + (1 - MIN_CRUISE_SHARE) * min(max(urgency, 0.0), 1.0))
    arrive = math.sqrt(2.0 * DECEL_MAX * ARRIVAL_SLACK * dist)
    desired_speed = min(cruise, arrive)
    desired = to_target / dist * desired_speed if dist > 1e-9 else np.zeros(2)

    speed = float(np.hypot(*state.vel))
    dv = desired - state.vel
    cap = (DECEL_MAX if desired_speed < speed else A_MAX) * dt
    dv_norm = float(np.hypot(*dv))
    if dv_norm > cap:
        dv = dv * (cap / dv_norm)
    vel = state.vel + dv
    new_speed = float(np.hypot(*vel))
    hard_cap = v_max(attrs.pace)
    if new_speed > hard_cap:
        vel = vel * (hard_cap / new_speed)
        new_speed = hard_cap

    drain = DRAIN_K * new_speed**2 * _drain_factor(attrs.stamina) * dt
    recover = RECOVERY_RATE * (1.0 - state.energy) * dt if new_speed < RECOVERY_SPEED else 0.0
    energy = min(max(state.energy - drain + recover, 0.0), 1.0)
    return PlayerState(pos=state.pos + vel * dt, vel=vel, energy=energy)
