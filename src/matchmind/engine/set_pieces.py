"""Set pieces: corner delivery, aerial duels, direct free kicks, and penalties.

Positions are in the attacking team's frame (attacking toward d = 105). Duels are
decided by the `aerial` rating and height; the delivery's accuracy by `crossing`; a
direct free kick's chance by distance and `finishing`; a penalty scores about 76% of
the time, nudged by the taker's composure modifier.
"""

import math

import numpy as np

from matchmind.engine.decisions import shot_xg
from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH

PENALTY_SPOT = (PITCH_LENGTH - 11.0, PITCH_WIDTH / 2)
BOX_DEPTH_M, BOX_HALF_WIDTH_M = 16.5, 20.16
SIX_YARD_DEPTH_M, SIX_YARD_HALF_WIDTH_M = 5.5, 9.16
AERIAL_K = 3.0  # per unit of aerial rating difference
HEIGHT_K = 0.25  # per 10 cm of height difference
PENALTY_CONVERSION = 0.76
HEADER_FACTOR = 0.55  # a header is a worse chance than a shot from the same spot
CORNER_TARGET = (97.0, 34.0)  # around the penalty spot, toward goal
NEAR_POST_SHIFT_M = 3.0
DELIVERY_SD_M = (2.0, 6.0)  # base + (1 - crossing) * extra
FK_MIN_M, FK_MAX_M = 17.0, 30.0  # direct free kicks: outside the box, within 30 m
FK_XG_AT_18 = 0.10
FK_XG_DECAY_M = 9.0
CLAIM_BASE, CLAIM_SKILL = 0.45, 0.3


def in_box(p: tuple[float, float] | np.ndarray) -> bool:
    """Inside the attacked penalty area (team frame)."""
    return bool(
        p[0] >= PITCH_LENGTH - BOX_DEPTH_M and abs(p[1] - PITCH_WIDTH / 2) <= BOX_HALF_WIDTH_M
    )


def aerial_duel(
    rng: np.random.Generator, att_aerial: float, att_height_cm: float, def_aerial: float,
    def_height_cm: float,
) -> bool:  # fmt: skip
    """True if the attacker wins the header."""
    z = AERIAL_K * (att_aerial - def_aerial) + HEIGHT_K * (att_height_cm - def_height_cm) / 10
    return bool(rng.random() < 1.0 / (1.0 + math.exp(-z)))


def corner_delivery(rng: np.random.Generator, crossing: float, right_side: bool) -> np.ndarray:
    """Where the delivery comes down. `right_side`: taken from the w = 0 corner."""
    sd = DELIVERY_SD_M[0] + (1.0 - crossing) * DELIVERY_SD_M[1]
    near = -NEAR_POST_SHIFT_M if right_side else NEAR_POST_SHIFT_M
    d = CORNER_TARGET[0] + float(rng.normal(0.0, sd))
    w = CORNER_TARGET[1] + near + float(rng.normal(0.0, sd))
    return np.array([min(max(d, 80.0), PITCH_LENGTH - 0.5), min(max(w, 1.0), PITCH_WIDTH - 1.0)])


def keeper_claims(rng: np.random.Generator, landing: tuple[float, float] | np.ndarray,
                  gk_aerial: float) -> bool:  # fmt: skip
    """The keeper comes for balls dropping into his six-yard box."""
    six = landing[0] >= PITCH_LENGTH - SIX_YARD_DEPTH_M and (
        abs(landing[1] - PITCH_WIDTH / 2) <= SIX_YARD_HALF_WIDTH_M
    )
    return bool(six and rng.random() < CLAIM_BASE + CLAIM_SKILL * (gk_aerial - 0.5))


def header_xg(pos: tuple[float, float] | np.ndarray, attacks_right: bool) -> float:
    return HEADER_FACTOR * shot_xg(pos, attacks_right, 0.5)


def free_kick_xg(distance_m: float, finishing: float) -> float:
    """Direct free-kick chance quality; 0 outside the 17-30 m band."""
    if not FK_MIN_M <= distance_m <= FK_MAX_M:
        return 0.0
    base = FK_XG_AT_18 * math.exp(-(distance_m - 18.0) / FK_XG_DECAY_M)
    return base * (0.7 + 0.6 * finishing)


def penalty_scores(rng: np.random.Generator, composure_mult: float = 1.0) -> bool:
    """About 0.76; `composure_mult` is the taker's capped `decision_temperature` inverse."""
    return bool(rng.random() < min(PENALTY_CONVERSION * composure_mult, 0.95))
