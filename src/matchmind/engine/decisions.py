"""On-ball decisions: enumerate options, score them, choose with skill-dependent noise.

Each option is scored `pc_prob * xt_gain - risk` (`score_option`): `pc_prob` is the
offside-filtered pitch control at the option's end point (Task 6.1), `xt_gain` the xT
change, and `risk` the cost of losing the ball there, `(1 - pc) * (LOSS_COST +
opponent xT at the end)`, divided by the player's risk weight. Passes to teammates who
are visibly offside get `pc_prob = 0`. A shot scores `xg - xT(here)`: shoot when the
chance beats keeping the ball. `choose` is a softmax over min-max normalized scores
with temperature `0.05 + 0.6 * (1 - skill)`, so weaker players pick worse options more
often. Everything runs in the team frame (attacking toward x = 105).
"""

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH
from matchmind.schemas import TrackingFrame
from matchmind.stats.pitch_control import PCParams, offside_players, pitch_control_at
from matchmind.stats.xt import xt_value

OptionKind = Literal["pass", "through", "carry", "shot", "clear"]

PASS_MIN_M, PASS_MAX_M = 4.0, 60.0
PASS_LEAD_MAX_S = 1.0  # aim where a moving teammate will be
THROUGH_AHEAD_M = 5.0  # through balls go to teammates this much deeper than the carrier
THROUGH_LEAD_M = 7.0  # ... into the space this far ahead of them
THROUGH_MAX_M = 40.0
CARRY_M = 7.0
CARRY_ANGLES_DEG = (0.0, 35.0, -35.0)
SHOT_MAX_M = 30.0
CLEAR_DEPTH_M = 35.0  # own third
CLEAR_PRESSURE_M = 3.0
CLEAR_TO = (65.0, 10.0)  # team frame: long, toward the nearer touchline
LOSS_COST = 0.01
TEMP_BASE, TEMP_SKILL = 0.05, 0.6
GOAL = np.array([PITCH_LENGTH, PITCH_WIDTH / 2])  # team frame
GOAL_HALF_WIDTH = 3.66
XG_BIAS, XG_ANGLE, XG_DIST = -1.3, 1.6, -0.08


@dataclass(frozen=True)
class Option:
    kind: OptionKind
    target_player_id: str | None
    end: tuple[float, float]  # absolute
    score: float
    pc_prob: float = 1.0
    xt_gain: float = 0.0


@dataclass(frozen=True)
class DecisionContext:
    team_id: str
    attacks_right: bool
    xt: np.ndarray
    goalkeepers: frozenset[str] = frozenset()
    risk_weight: float = 1.0  # PlayerMods.risk_weight (>1 accepts more risk)
    pc_params: PCParams | None = None


def _local(p: np.ndarray, right: bool) -> np.ndarray:
    """Absolute <-> team frame (the map is its own inverse)."""
    return p if right else np.array([PITCH_LENGTH - p[0], PITCH_WIDTH - p[1]])


def _clamp(p: np.ndarray, margin: float = 1.0) -> np.ndarray:
    return np.array([min(max(float(p[0]), margin), PITCH_LENGTH - margin),
                     min(max(float(p[1]), margin), PITCH_WIDTH - margin)])  # fmt: skip


def score_option(pc_prob: float, xt_gain: float, risk: float) -> float:
    return pc_prob * xt_gain - risk


def shot_xg(pos: tuple[float, float] | np.ndarray, attacks_right: bool, skill: float) -> float:
    """Chance quality from distance and the goal's opening angle, nudged by skill."""
    here = _local(np.asarray(pos, dtype=float), attacks_right)
    dx = PITCH_LENGTH - float(here[0])
    dy = abs(PITCH_WIDTH / 2 - float(here[1]))
    dist = math.hypot(dx, dy)
    angle = abs(math.atan2(dy + GOAL_HALF_WIDTH, dx) - math.atan2(dy - GOAL_HALF_WIDTH, dx))
    xg = 1.0 / (1.0 + math.exp(-(XG_BIAS + XG_ANGLE * angle + XG_DIST * dist)))
    return float(min(max(xg * (0.85 + 0.3 * skill), 0.005), 0.95))


def _value(grid: np.ndarray, local: np.ndarray) -> float:
    return xt_value(grid, float(local[0]), float(local[1]))


def enumerate_options(frame: TrackingFrame, carrier_id: str, ctx: DecisionContext) -> list[Option]:
    """Passes, through balls, carries, a shot within 30 m, and a clearance when pressed
    in the own third; each scored with offside-filtered pitch control."""
    right = ctx.attacks_right
    by_id = {p.player_id: p for p in frame.players}
    me = by_id[carrier_id]
    here_abs = np.array([me.x, me.y])
    here = _local(here_abs, right)
    mates = [p for p in frame.players if p.team_id == ctx.team_id and p.player_id != carrier_id]
    opps = [p for p in frame.players if p.team_id != ctx.team_id]
    offside = offside_players(frame, ctx.team_id, right)

    raw: list[tuple[OptionKind, str | None, np.ndarray]] = []  # (kind, target, local end)
    for p in mates:
        pos, vel = np.array([p.x, p.y]), np.array([p.vx, p.vy])
        d = float(np.hypot(*(pos - here_abs)))
        if PASS_MIN_M <= d <= PASS_MAX_M:
            lead = min(d / 15.0, PASS_LEAD_MAX_S)
            raw.append(("pass", p.player_id, _clamp(_local(pos + vel * lead, right))))
        mate = _local(pos, right)
        if mate[0] > here[0] + THROUGH_AHEAD_M and d <= THROUGH_MAX_M:
            ahead = np.array([mate[0] + THROUGH_LEAD_M, mate[1]])
            raw.append(("through", p.player_id, _clamp(ahead)))
    for deg in CARRY_ANGLES_DEG:
        a = math.radians(deg)
        raw.append(("carry", None, _clamp(here + CARRY_M * np.array([math.cos(a), math.sin(a)]))))
    pressed = min((math.hypot(p.x - me.x, p.y - me.y) for p in opps), default=99.0)
    if here[0] < CLEAR_DEPTH_M and pressed < CLEAR_PRESSURE_M:
        w = CLEAR_TO[1] if here[1] < PITCH_WIDTH / 2 else PITCH_WIDTH - CLEAR_TO[1]
        raw.append(("clear", None, np.array([CLEAR_TO[0], w])))

    ends_abs = np.array([_local(e, right) for _, _, e in raw]).reshape(-1, 2)
    pc = pitch_control_at(frame, ctx.team_id, ends_abs, params=ctx.pc_params,
                          goalkeepers=ctx.goalkeepers, attacks_right=right)  # fmt: skip
    start_value = _value(ctx.xt, here)
    options: list[Option] = []
    for (kind, target, end), prob, end_abs in zip(raw, pc, ends_abs, strict=True):
        p_ok = 0.0 if target in offside else float(prob)
        gain = _value(ctx.xt, end) - start_value
        lost_at = np.array([PITCH_LENGTH - end[0], PITCH_WIDTH - end[1]])
        risk = (1.0 - p_ok) * (LOSS_COST + _value(ctx.xt, lost_at)) / ctx.risk_weight
        options.append(Option(kind, target, (float(end_abs[0]), float(end_abs[1])),
                              score_option(p_ok, gain, risk), p_ok, gain))  # fmt: skip
    goal_dist = float(np.hypot(*(GOAL - here)))
    if goal_dist <= SHOT_MAX_M:
        xg = shot_xg(here_abs, right, 0.5)
        goal_abs = _local(GOAL, right)
        options.append(Option("shot", None, (float(goal_abs[0]), float(goal_abs[1])),
                              xg - start_value, xg, 1.0 - start_value))  # fmt: skip
    return options


def choose(
    options: list[Option], skill: float, rng: np.random.Generator, temperature_mult: float = 1.0
) -> Option:
    """Softmax over min-max normalized scores; `temperature_mult` is the player's
    `decision_temperature` modifier (composure under pressure)."""
    scores = np.array([o.score for o in options], dtype=float)
    span = float(scores.max() - scores.min())
    norm = (scores - scores.max()) / span if span > 1e-12 else np.zeros(len(scores))
    temp = (TEMP_BASE + TEMP_SKILL * (1.0 - skill)) * temperature_mult
    weights = np.exp(norm / temp)
    cum = np.cumsum(weights)
    idx = int(np.searchsorted(cum, rng.random() * cum[-1], side="right"))
    return options[min(idx, len(options) - 1)]


def decision_extras(chosen: Option, options: list[Option]) -> dict[str, object]:
    best = max(options, key=lambda o: o.score)
    return {
        "chosen_score": round(chosen.score, 4),
        "best_score": round(best.score, 4),
        "best_option": {
            "kind": best.kind,
            "target": best.target_player_id,
            "end": [round(best.end[0], 2), round(best.end[1], 2)],
        },  # fmt: skip
    }
