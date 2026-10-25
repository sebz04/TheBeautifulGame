"""Counterfactuals: what else the player could have done, scored the way the engine did.

The scorer is literally the engine's: `engine.decisions.enumerate_options`,
`score_option`, `filter_options`, and the engine's own `decision_context`. The decision
frame is rebuilt from the stored match (`decision_frame`): positions and velocities as
the player perceived them (`PERCEPTION_LAG_TICKS` + 1 frames before the kick) and the ball
where it was kicked from. The player's risk modifier and any goal-beat window come from
the event's extras. Stored frames are rounded to 1 cm, so scores match the engine's
`best_score` to about 1e-5, not exactly.
"""

import math
from collections.abc import Collection

import numpy as np
from pydantic import BaseModel

from matchmind.engine import constants as C
from matchmind.engine.coupled import decision_context
from matchmind.engine.decisions import Option, enumerate_options, filter_options
from matchmind.engine.pitch import attacks_right as team_attacks_right
from matchmind.schemas import Event, MatchData, TrackingFrame, trusted

DECISION_TYPES = frozenset({"pass", "carry", "shot", "clearance"})


class Counterfactual(BaseModel):
    event_id: str
    chosen: Option
    best: Option
    gain: float  # best.score - chosen.score (>= 0)
    alternatives: list[Option]  # best first


def decision_frame(match: MatchData, event: Event) -> TrackingFrame:
    """The pitch as the player saw it when deciding (the engine's lagged frame)."""
    period = [f for f in match.frames if f.period == event.period]
    if not period:
        raise ValueError(f"no frames for period {event.period}")
    k = round(event.t / C.DT)
    seen = period[min(max(k - C.PERCEPTION_LAG_TICKS - 1, 0), len(period) - 1)]
    ball_z = period[min(max(k - 1, 0), len(period) - 1)].ball[2]
    return trusted(TrackingFrame, {**seen.__dict__, "ball": (event.x, event.y, ball_z)})


def _pick_chosen(options: list[Option], played: dict[str, object]) -> Option:
    same = [o for o in options if o.kind == played.get("kind")
            and o.target_player_id == played.get("target")]  # fmt: skip
    end = played.get("end") or [0.0, 0.0]
    pool = same or options
    return min(pool, key=lambda o: math.dist(o.end, (float(end[0]), float(end[1]))))  # type: ignore[index]


def counterfactual(
    event: Event,
    frame: TrackingFrame,
    xt_grid: np.ndarray,
    attacks_right: bool,
    goalkeepers: Collection[str] = frozenset(),
) -> Counterfactual:
    """All options the player had at `event`, scored; `frame` is its `decision_frame`."""
    if event.type not in DECISION_TYPES or "best_score" not in event.extras:
        raise ValueError(f"{event.event_id} is not a decision event")
    if event.player_id is None:
        raise ValueError(f"{event.event_id} has no player")
    ex = event.extras
    keepers = frozenset(goalkeepers)
    risk, window = float(ex.get("risk_weight", 1.0)), bool(ex.get("goal_window"))
    ctx = decision_context(event.team_id, attacks_right, xt_grid, keepers, risk, window)
    options = enumerate_options(frame, event.player_id, ctx)
    options = filter_options(options, ex.get("restart"), event.player_id in keepers,
                             (event.x, event.y))  # fmt: skip
    ranked = sorted(options, key=lambda o: o.score, reverse=True)
    chosen = _pick_chosen(ranked, ex.get("chosen_option") or {})
    return Counterfactual(event_id=event.event_id, chosen=chosen, best=ranked[0],
                          gain=ranked[0].score - chosen.score, alternatives=ranked)  # fmt: skip


def match_counterfactuals(match: MatchData, xt_grid: np.ndarray) -> list[Counterfactual]:
    """A counterfactual for every decision event of a match with frames."""
    home = match.meta.home.club_id
    keepers = frozenset({match.meta.home_squad[0].player_id, match.meta.away_squad[0].player_id})
    out = []
    for e in match.events:
        if e.type in DECISION_TYPES and "best_score" in e.extras:
            right = team_attacks_right(e.team_id == home, e.period)
            out.append(counterfactual(e, decision_frame(match, e), xt_grid, right, keepers))
    return out
