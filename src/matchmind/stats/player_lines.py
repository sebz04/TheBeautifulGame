"""One line of stats per player per match, from the match's events and the engine's motion.

Used for season history (TASK-10.4) and, through the same function, for live matches.
Definitions, in the acting team's frame (attacking toward x = 105):
- forward pass: gains at least `FORWARD_M` of depth; progressive pass: completed and
  brings the ball at least `PROGRESSIVE_M` and `PROGRESSIVE_SHARE` closer to goal.
- key pass / assist: a completed pass whose receiver's next action is a shot / a goal
  (with only his own carries in between).
- shot on target: it scored or the next event is the opponent's save.
- box touch: a pass, carry, or shot from the opponent's box, or a pass received there.
"""

from collections import defaultdict
from collections.abc import Mapping

import numpy as np
from pydantic import BaseModel

from matchmind.engine.coupled import Motion
from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH, attacks_right
from matchmind.engine.set_pieces import in_box
from matchmind.schemas import MatchData
from matchmind.stats.xt import load_xt, xt_added

FORWARD_M = 5.0
PROGRESSIVE_M = 10.0
PROGRESSIVE_SHARE = 0.75
_ON_BALL = frozenset({"pass", "carry", "shot", "clearance", "tackle", "interception"})


class PlayerMatchLine(BaseModel):
    match_id: str
    round: int
    player_id: str
    club_id: str
    minutes: int
    passes: int = 0
    completed: int = 0
    forward_passes: int = 0
    progressive_passes: int = 0
    key_passes: int = 0
    xt_added: float = 0.0
    shots: int = 0
    shots_on_target: int = 0
    xg: float = 0.0
    dribbles: int = 0
    tackles: int = 0
    interceptions: int = 0
    pressures: int = 0
    fouls: int = 0
    distance_km: float = 0.0
    sprints: int = 0
    top_speed_ms: float = 0.0
    box_touches: int = 0
    goals: int = 0
    assists: int = 0
    yellow: int = 0
    red: int = 0


def _local(x: float, y: float, right: bool) -> np.ndarray:
    return np.array([x, y]) if right else np.array([PITCH_LENGTH - x, PITCH_WIDTH - y])


def _goal_dist(p: np.ndarray) -> float:
    return float(np.hypot(PITCH_LENGTH - p[0], PITCH_WIDTH / 2 - p[1]))


def player_match_lines(
    data: MatchData, motion: Mapping[str, Motion], round_: int, xt: np.ndarray | None = None
) -> list[PlayerMatchLine]:
    """A line for every player who appeared (has a `Motion`), in squad order."""
    grid = load_xt() if xt is None else xt
    home = data.meta.home.club_id
    club_of = {p.player_id: p.club_id for p in data.meta.home_squad + data.meta.away_squad}
    stats: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    events = data.events
    chain: tuple[str, str] | None = None  # (receiver, passer) of the last completed pass
    for n, e in enumerate(events):
        pid = e.player_id
        if pid is None:
            continue
        s = stats[pid]
        right = attacks_right(e.team_id == home, e.period)
        start = _local(e.x, e.y, right)
        if e.type in _ON_BALL and chain is not None and pid != chain[0]:
            chain = None
        if e.type == "pass":
            s["passes"] += 1
            if e.end_x is not None and e.end_y is not None:
                end = _local(e.end_x, e.end_y, right)
                s["forward_passes"] += end[0] - start[0] >= FORWARD_M
                if e.outcome:
                    gain = _goal_dist(start) - _goal_dist(end)
                    closer = _goal_dist(end) <= PROGRESSIVE_SHARE * _goal_dist(start)
                    s["progressive_passes"] += gain >= PROGRESSIVE_M and closer
                    if e.receiver_id is not None and in_box(end):
                        stats[e.receiver_id]["box_touches"] += 1
            if e.outcome:
                s["completed"] += 1
                chain = (e.receiver_id, pid) if e.receiver_id is not None else None
        elif e.type == "carry":
            s["dribbles"] += 1
        elif e.type == "shot":
            s["shots"] += 1
            s["xg"] += float(e.extras.get("xg", 0.0))
            saved = n + 1 < len(events) and events[n + 1].type == "save"
            s["shots_on_target"] += bool(e.outcome) or saved
            if chain is not None and chain[0] == pid:
                stats[chain[1]]["key_passes"] += 1
                stats[chain[1]]["assists"] += bool(e.outcome)
            chain = None
        elif e.type == "goal" and not e.extras.get("own_goal"):
            s["goals"] += 1
        elif e.type in ("tackle", "interception", "pressure", "foul"):
            s[{"tackle": "tackles", "interception": "interceptions", "pressure": "pressures",
               "foul": "fouls"}[e.type]] += 1  # fmt: skip
        elif e.type == "card":
            s["yellow" if e.extras.get("card") == "yellow" else "red"] += 1
        if e.type in ("pass", "carry", "shot") and in_box(start):
            s["box_touches"] += 1
        if e.type in ("pass", "carry") and e.outcome:
            added = xt_added(grid, e, right)
            s["xt_added"] += added or 0.0
    lines = []
    for pid in (p.player_id for p in data.meta.home_squad + data.meta.away_squad):
        if pid not in motion:
            continue
        m, s = motion[pid], stats[pid]
        counts = {k: int(v) for k, v in s.items() if k not in ("xg", "xt_added")}
        lines.append(PlayerMatchLine(
            match_id=data.meta.match_id, round=round_, player_id=pid, club_id=club_of[pid],
            minutes=round(m.minutes), distance_km=round(m.distance_m / 1000, 3),
            sprints=m.sprints, top_speed_ms=round(m.top_speed_ms, 2),
            xg=round(s["xg"], 3), xt_added=round(s["xt_added"], 4), **counts,
        ))  # fmt: skip
    return lines
