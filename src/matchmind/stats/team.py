"""Team metrics over a window of the match: PPDA, field tilt, momentum, control vs chaos.

Windows are (period, t) pairs, inclusive, since `t` restarts each half. Depths are
measured from a team's own goal line (`engine.pitch.attacks_right`).
- PPDA: opponent passes in their own 60% ÷ our tackles, interceptions, and fouls in that
  zone; None when we made no such action (never infinite).
- Field tilt: our share of the passes played in a final third.
- Momentum: per team, xT added by completed passes and carries plus shot xG over the
  last `window_s` (within the same half), sampled every `step_s`; `diff` = home − away.
- Control vs chaos, in [0, 1]: a weighted mean of four parts, each scaled so a typical
  match sits near 0.5: turnover rate, short possessions, pitch-control volatility (needs
  frames; skipped without them), and the share of long forward passes.
"""

import math
from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel

from matchmind.engine.pitch import PITCH_LENGTH, attacks_right
from matchmind.engine.realism_ranges import PPDA_ZONE_SHARE
from matchmind.schemas import Event, TrackingFrame
from matchmind.stats.pitch_control import pitch_control_grid
from matchmind.stats.xt import xt_added

MatchTime = tuple[int, float]
DEFENSIVE_ACTIONS = frozenset({"tackle", "interception", "foul"})
ON_BALL = frozenset({"pass", "carry", "shot", "tackle", "interception", "clearance"})
FINAL_THIRD_M = 70.0
LONG_BALL_M = 30.0
# Typical values ("midpoints"): each chaos part is value / (2 * midpoint), clipped.
TURNOVER_MID = 0.12  # possession changes per on-ball event
POSSESSION_MID = 6.0  # on-ball events per possession (fewer = more chaotic)
PC_VOLATILITY_MID = 0.04  # SD of the home team's mean pitch control, sampled every 10 s
DIRECT_MID = 0.15  # share of passes that are long and forward
CHAOS_WEIGHTS = {"turnovers": 0.4, "short": 0.3, "volatility": 0.15, "direct": 0.15}
PC_SAMPLE_S = 10.0


def _in(e: Event | TrackingFrame, t_from: MatchTime, t_to: MatchTime) -> bool:
    return t_from <= (e.period, e.t) <= t_to


def _depth(x: float, team_id: str, home_id: str, period: int) -> float:
    """Distance from the team's own goal line along the pitch."""
    return x if attacks_right(team_id == home_id, period) else PITCH_LENGTH - x


def ppda(events: Sequence[Event], team_id: str, home_id: str, t_from: MatchTime,
         t_to: MatchTime) -> float | None:  # fmt: skip
    passes = actions = 0
    for e in events:
        if not _in(e, t_from, t_to):
            continue
        depth = _depth(e.x, e.team_id, home_id, e.period)
        if e.type == "pass" and e.team_id != team_id and depth < PPDA_ZONE_SHARE * PITCH_LENGTH:
            passes += 1
        own = e.team_id == team_id
        if own and e.type in DEFENSIVE_ACTIONS and depth > (1 - PPDA_ZONE_SHARE) * PITCH_LENGTH:
            actions += 1
    return passes / actions if actions else None


def field_tilt(events: Sequence[Event], team_id: str, home_id: str, t_from: MatchTime,
               t_to: MatchTime) -> float:  # fmt: skip
    ours = total = 0
    for e in events:
        in_final_third = _depth(e.x, e.team_id, home_id, e.period) >= FINAL_THIRD_M
        if e.type == "pass" and _in(e, t_from, t_to) and in_final_third:
            total += 1
            ours += e.team_id == team_id
    return ours / total if total else 0.5


class MomentumPoint(BaseModel):
    period: int
    t: float
    home: float
    away: float
    diff: float  # home - away


class MomentumSeries(BaseModel):
    window_s: float
    step_s: float
    points: list[MomentumPoint]

    def at(self, period: int, t: float) -> MomentumPoint | None:
        """The last point at or before (period, t)."""
        best = None
        for p in self.points:
            if (p.period, p.t) <= (period, t):
                best = p
        return best


def momentum_series(events: Sequence[Event], xt_grid: np.ndarray, home_id: str,
                    window_s: float = 300.0, step_s: float = 30.0) -> MomentumSeries:  # fmt: skip
    values: list[tuple[int, float, bool, float]] = []  # (period, t, is_home, value)
    for e in events:
        if e.type == "shot":
            v = float(e.extras.get("xg", 0.0))
        elif e.type in ("pass", "carry") and e.outcome:
            v = xt_added(xt_grid, e, attacks_right(e.team_id == home_id, e.period)) or 0.0
        else:
            continue
        values.append((e.period, e.t, e.team_id == home_id, v))
    points = []
    for period in sorted({p for p, *_ in values} or {1}):
        mine = [v for v in values if v[0] == period]
        last = max((t for _, t, _, _ in mine), default=0.0)
        for k in range(math.ceil(last / step_s) + 1):
            t = k * step_s
            window = [(home, v) for _, te, home, v in mine if t - window_s < te <= t]
            h = sum(v for home, v in window if home)
            a = sum(v for home, v in window if not home)
            points.append(MomentumPoint(period=period, t=t, home=round(h, 4), away=round(a, 4),
                                        diff=round(h - a, 4)))  # fmt: skip
    return MomentumSeries(window_s=window_s, step_s=step_s, points=points)


def _pc_volatility(frames: Sequence[TrackingFrame], home_id: str, t_from: MatchTime,
                   t_to: MatchTime) -> float | None:  # fmt: skip
    every = round(PC_SAMPLE_S * 10)
    sampled = [f for f in frames if _in(f, t_from, t_to) and round(f.t * 10) % every == 0]
    if len(sampled) < 3:
        return None
    means = [float(pitch_control_grid(f, home_id, nx=16, ny=10).mean()) for f in sampled]
    return float(np.std(means))


def control_chaos(events: Sequence[Event], frames: Sequence[TrackingFrame], t_from: MatchTime,
                  t_to: MatchTime, home_id: str) -> float:  # fmt: skip
    """0 = control (long, patient possessions), 1 = chaos (turnovers, long balls)."""
    seq = [e for e in events if e.type in ON_BALL and _in(e, t_from, t_to)]
    parts: dict[str, float] = {}
    if len(seq) >= 2:
        changes = sum(a.team_id != b.team_id for a, b in zip(seq, seq[1:], strict=False))
        parts["turnovers"] = min(changes / (len(seq) - 1) / (2 * TURNOVER_MID), 1.0)
        length = len(seq) / (changes + 1)
        parts["short"] = min(max(1.0 - length / (2 * POSSESSION_MID), 0.0), 1.0)
    passes = [e for e in seq if e.type == "pass" and e.end_x is not None]
    if passes:
        long_fwd = sum(_gain(e, home_id) >= LONG_BALL_M for e in passes)
        parts["direct"] = min(long_fwd / len(passes) / (2 * DIRECT_MID), 1.0)
    vol = _pc_volatility(frames, home_id, t_from, t_to)
    if vol is not None:
        parts["volatility"] = min(vol / (2 * PC_VOLATILITY_MID), 1.0)
    if not parts:
        return 0.5
    weight = sum(CHAOS_WEIGHTS[k] for k in parts)
    return float(sum(CHAOS_WEIGHTS[k] * v for k, v in parts.items()) / weight)


def _gain(e: Event, home_id: str) -> float:
    """Metres a pass moved the ball toward the passer's attacking goal."""
    assert e.end_x is not None
    return (e.end_x - e.x) * (1.0 if attacks_right(e.team_id == home_id, e.period) else -1.0)
