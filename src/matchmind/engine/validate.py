"""Realism checks: compare a match's team stats with `RANGES`.

Possession is the share of passes (the engine has no possession clock). Distance and
speed come from the tracking frames; a sprint is above 7.0 m/s for at least 1 s.
Throw-ins, goal kicks, and corners are counted for the team awarded them: the opponent
of the team whose last touch put the ball out (`out` events' `extras.restart`).
"""

from collections import defaultdict
from collections.abc import Iterable

import numpy as np
from pydantic import BaseModel

from matchmind.engine.pitch import PITCH_LENGTH, attacks_right
from matchmind.engine.realism_ranges import (
    PPDA_ZONE_SHARE,
    RANGES,
    SPRINT_MIN_S,
    SPRINT_SPEED_MS,
)
from matchmind.schemas import MatchData

DT = 0.1
_DEFENSIVE_ACTIONS = {"tackle", "interception", "foul"}


class Check(BaseModel):
    name: str
    value: float
    lo: float
    hi: float
    ok: bool
    in_range_share: float | None = None  # validate_many: share of team-matches in range


class RealismReport(BaseModel):
    checks: list[Check]
    ok: bool


def _check(name: str, metric: str, value: float) -> Check:
    lo, hi = RANGES[metric]
    return Check(name=name, value=value, lo=lo, hi=hi, ok=bool(lo <= value <= hi))


def _event_stats(data: MatchData) -> dict[str, dict[str, float]]:
    home_id, away_id = data.meta.home.club_id, data.meta.away.club_id
    count: dict[str, dict[str, int]] = {t: defaultdict(int) for t in (home_id, away_id)}
    awarded: dict[str, dict[str, int]] = {t: defaultdict(int) for t in (home_id, away_id)}
    other = {home_id: away_id, away_id: home_id}
    build_up: dict[str, int] = defaultdict(int)  # passes in the team's own 60%
    high_actions: dict[str, int] = defaultdict(int)  # defensive actions in the opponent's 60%
    for e in data.events:
        team = e.team_id
        c = count[team]
        c[e.type] += 1
        if e.type == "pass" and e.outcome:
            c["completed"] += 1
        if e.type == "out" and "restart" in e.extras:
            awarded[other[team]][e.extras["restart"]] += 1
        right = attacks_right(team == home_id, e.period)
        depth = e.x if right else PITCH_LENGTH - e.x  # distance from own goal line
        if e.type == "pass" and depth < PPDA_ZONE_SHARE * PITCH_LENGTH:
            build_up[team] += 1
        if e.type in _DEFENSIVE_ACTIONS and depth > (1 - PPDA_ZONE_SHARE) * PITCH_LENGTH:
            high_actions[team] += 1
    total_passes = count[home_id]["pass"] + count[away_id]["pass"]
    out: dict[str, dict[str, float]] = {}
    for team, opp in ((home_id, away_id), (away_id, home_id)):
        c = count[team]
        shots = c["shot"]
        on_target = c["goal"] + count[opp]["save"]
        out[team] = {
            "passes": c["pass"],
            "pass_completion": c["completed"] / c["pass"] if c["pass"] else 0.0,
            "shots": shots,
            "shots_on_target_ratio": on_target / shots if shots else 0.0,
            "possession": c["pass"] / total_passes if total_passes else 0.5,
            # No high defensive actions at all: count as one, so PPDA stays finite (JSON-safe).
            "ppda": build_up[opp] / max(high_actions[team], 1),
            "tackles": c["tackle"],
            "offsides": c["offside"],
            "throw_ins": awarded[team]["throw_in"],
            "goal_kicks": awarded[team]["goal_kick"],
            "corners": awarded[team]["corner"],
            "fouls": c["foul"],
            "goals": c["goal"],
        }
    return out


def _sprints(speed: np.ndarray) -> int:
    fast = np.concatenate([[False], speed > SPRINT_SPEED_MS, [False]])
    edges = np.flatnonzero(np.diff(fast.astype(np.int8)))
    runs = edges[1::2] - edges[::2]
    return int(np.sum(runs * DT >= SPRINT_MIN_S - 1e-9))


def _tracking_stats(data: MatchData) -> dict[str, dict[str, float]]:
    """Outfield players only (goalkeepers are the first player of each squad's XI)."""
    keepers = {p.player_id for p in data.meta.home_squad + data.meta.away_squad
               if p.position == "GK"}  # fmt: skip
    xy: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
    speed: dict[tuple[str, int], list[float]] = defaultdict(list)
    team_of: dict[str, str] = {}
    for f in data.frames:
        for p in f.players:
            if p.player_id in keepers:
                continue
            key = (p.player_id, f.period)
            xy[key].append((p.x, p.y))
            speed[key].append((p.vx**2 + p.vy**2) ** 0.5)
            team_of[p.player_id] = p.team_id
    dist: dict[str, float] = defaultdict(float)
    top: dict[str, float] = defaultdict(float)
    sprints: dict[str, int] = defaultdict(int)
    for (pid, _period), points in xy.items():
        arr = np.asarray(points)
        dist[pid] += float(np.hypot(*np.diff(arr, axis=0).T).sum()) if len(arr) > 1 else 0.0
        sp = np.asarray(speed[(pid, _period)])
        top[pid] = max(top[pid], float(sp.max()))
        sprints[pid] += _sprints(sp)
    out: dict[str, dict[str, float]] = {}
    for team in (data.meta.home.club_id, data.meta.away.club_id):
        players = [pid for pid, t in team_of.items() if t == team]
        n = max(len(players), 1)
        out[team] = {
            "distance_km_outfield_player": sum(dist[p] for p in players) / n / 1000,
            "top_speed_ms": max((top[p] for p in players), default=0.0),
            "sprints_per_outfield_player": sum(sprints[p] for p in players) / n,
        }
    return out


def team_stats(data: MatchData) -> dict[str, dict[str, float]]:
    """Every per-team metric in `RANGES` (plus `goals`), keyed by club id."""
    events, tracking = _event_stats(data), _tracking_stats(data)
    return {team: {**events[team], **tracking[team]} for team in events}


def _per_team_metrics() -> list[str]:
    return [m for m in RANGES if m != "goals_per_match"]


def validate_match(data: MatchData) -> RealismReport:
    stats = team_stats(data)
    checks = [
        _check(f"{metric}:{team}", metric, values[metric])
        for team, values in stats.items()
        for metric in _per_team_metrics()
    ]
    return RealismReport(checks=checks, ok=all(c.ok for c in checks))


def validate_many(datas: Iterable[MatchData]) -> RealismReport:
    """Mean of each metric over all team-matches, plus mean goals per match.

    Consumes the matches one at a time, so a generator keeps memory flat.
    """
    values: dict[str, list[float]] = defaultdict(list)
    goals: list[float] = []
    for data in datas:
        stats = team_stats(data)
        goals.append(sum(v["goals"] for v in stats.values()))
        for team_values in stats.values():
            for metric in _per_team_metrics():
                values[metric].append(team_values[metric])
    checks = []
    for metric in _per_team_metrics():
        vs = np.asarray(values[metric], dtype=float)
        c = _check(metric, metric, float(vs.mean()) if len(vs) else 0.0)
        lo, hi = RANGES[metric]
        c.in_range_share = float(np.mean((vs >= lo) & (vs <= hi))) if len(vs) else 0.0
        checks.append(c)
    checks.append(_check("goals_per_match", "goals_per_match", float(np.mean(goals))))
    return RealismReport(checks=checks, ok=all(c.ok for c in checks))
