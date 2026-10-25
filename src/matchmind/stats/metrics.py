"""Metric materialization: every team and player metric at a moment, from data up to it.

Two paths over the same code (`snapshot`):
- `metrics_at(match, xt_grid, period, t, scope, scope_id)`: event-exact and on demand.
  It reads only events and frames at or before (period, t), so deleting everything later
  changes nothing. Pitch-control territory is evaluated once, at the latest event.
- `compute_metrics(match, xt_grid, step_s=30, extra_times=...)`: stores the snapshot on
  a 30 s grid (`kind="grid"`) plus at each extra time, such as every moment's end
  (`kind="moment"`), so a moment's numbers are exactly the ones its insight cites.
Running (distance, speed, sprints) comes from tracking (`stats.speed`); per-event values
(xT added, pass quality, chance quality) are computed per event, not snapshotted.
"""

import bisect
from collections.abc import Sequence

import numpy as np

from matchmind.engine.coupled import Motion
from matchmind.engine.pitch import attacks_right
from matchmind.schemas import Event, MatchData, MetricRow, TrackingFrame
from matchmind.stats.deviations import minutes_played
from matchmind.stats.pitch_control import pitch_control_grid
from matchmind.stats.player_lines import player_match_lines
from matchmind.stats.team import control_chaos, field_tilt, ppda
from matchmind.stats.xt import xt_added

MatchTime = tuple[int, float]
Snapshot = dict[tuple[str, str], dict[str, float]]  # (scope, scope_id) -> name -> value
WINDOW_S = 600.0  # the "last 10 minutes" metrics
MOMENTUM_S = 300.0
TEAM_METRICS: tuple[str, ...] = (
    "goals", "shots", "shots_on_target", "xg", "passes", "pass_completion", "possession",
    "ppda", "ppda_10min", "field_tilt_10min", "momentum", "control_chaos", "territory",
    "corners", "fouls", "offsides", "yellow", "red", "players",
)  # fmt: skip
PLAYER_METRICS: tuple[str, ...] = (
    "minutes", "passes", "completed", "pass_accuracy", "forward_passes", "progressive_passes",
    "key_passes", "xt_added", "shots", "xg", "goals", "assists", "tackles", "interceptions",
    "dribbles", "fouls",
)  # fmt: skip


def _team_stats(match: MatchData, upto: Sequence[Event], grid: np.ndarray, period: int,
                t: float) -> dict[str, dict[str, float]]:  # fmt: skip
    home, away = match.meta.home.club_id, match.meta.away.club_id
    other = {home: away, away: home}
    out: dict[str, dict[str, float]] = {home: {}, away: {}}
    passes = {home: 0, away: 0}
    for team in (home, away):
        s = out[team]
        for name in ("goals", "shots", "shots_on_target", "xg", "corners", "fouls", "offsides",
                     "yellow", "red", "momentum"):  # fmt: skip
            s[name] = 0.0
    completed = {home: 0, away: 0}
    for n, e in enumerate(upto):
        s = out[e.team_id]
        if e.type == "goal":
            s["goals"] += 1
        elif e.type == "shot":
            s["shots"] += 1
            s["xg"] += float(e.extras.get("xg", 0.0))
            saved = n + 1 < len(upto) and upto[n + 1].type == "save"
            s["shots_on_target"] += bool(e.outcome) or saved
        elif e.type == "pass":
            passes[e.team_id] += 1
            completed[e.team_id] += bool(e.outcome)
        elif e.type == "out" and e.extras.get("restart") == "corner":
            out[other[e.team_id]]["corners"] += 1
        elif e.type in ("foul", "offside"):
            s["fouls" if e.type == "foul" else "offsides"] += 1
        elif e.type == "card":
            s["yellow" if e.extras.get("card") == "yellow" else "red"] += 1
        # Momentum: xT added and shot xG over the last 5 minutes of this half.
        if e.period == period and t - MOMENTUM_S < e.t <= t:
            if e.type == "shot":
                s["momentum"] += float(e.extras.get("xg", 0.0))
            elif e.type in ("pass", "carry") and e.outcome:
                s["momentum"] += (
                    xt_added(grid, e, attacks_right(e.team_id == home, e.period)) or 0.0
                )
    total = passes[home] + passes[away]
    start: MatchTime = (period, max(t - WINDOW_S, 0.0))
    for team in (home, away):
        s = out[team]
        if passes[team]:
            s["pass_completion"] = completed[team] / passes[team]
        s["passes"] = float(passes[team])
        s["possession"] = passes[team] / total if total else 0.5
        whole = ppda(upto, team, home, (1, 0.0), (period, t))
        recent = ppda(upto, team, home, start, (period, t))
        if whole is not None:
            s["ppda"] = whole
        if recent is not None:
            s["ppda_10min"] = recent
        s["field_tilt_10min"] = field_tilt(upto, team, home, start, (period, t))
        s["control_chaos"] = control_chaos(upto, [], start, (period, t), home)
        s["players"] = 11.0 - s["red"]  # on the pitch: agents may say "ten men" with a ref
    return out


def _frame_at(frames: Sequence[TrackingFrame], when: MatchTime) -> TrackingFrame | None:
    """The last frame at or before `when` (frames are in time order)."""
    keys = [(f.period, f.t) for f in frames]
    i = bisect.bisect_right(keys, when) - 1
    return frames[i] if i >= 0 else None


def _territory(match: MatchData, upto: Sequence[Event]) -> float | None:
    """Home team's mean pitch control (16 x 10 grid) at the latest event so far."""
    if not upto or not match.frames:
        return None
    last = upto[-1]
    frame = _frame_at(match.frames, (last.period, last.t))
    if frame is None:
        return None
    home = match.meta.home.club_id
    keepers = frozenset({match.meta.home_squad[0].player_id, match.meta.away_squad[0].player_id})
    grid = pitch_control_grid(frame, home, nx=16, ny=10, goalkeepers=keepers,
                              attacks_right=attacks_right(True, frame.period))  # fmt: skip
    return float(grid.mean())


def snapshot(match: MatchData, grid: np.ndarray, period: int, t: float) -> Snapshot:
    when = (period, t)
    upto = [e for e in match.events if (e.period, e.t) <= when]
    home, away = match.meta.home.club_id, match.meta.away.club_id
    snap: Snapshot = {}
    teams = _team_stats(match, upto, grid, period, t)
    territory = _territory(match, upto)
    for team, values in teams.items():
        if territory is not None:
            values["territory"] = territory if team == home else 1.0 - territory
        snap[("team", team)] = values
    snap[("team", home)].setdefault("momentum", 0.0)
    snap[("team", away)].setdefault("momentum", 0.0)
    played = minutes_played(match, when)
    motion = {pid: Motion(minutes=m) for pid, m in played.items() if m > 0}
    cut = match.model_copy(update={"events": upto})
    for line in player_match_lines(cut, motion, round_=0, xt=grid):
        values = {name: float(getattr(line, name)) for name in PLAYER_METRICS
                  if name not in ("minutes", "pass_accuracy")}  # fmt: skip
        values["minutes"] = round(played[line.player_id], 2)
        if line.passes:
            values["pass_accuracy"] = line.completed / line.passes
        snap[("player", line.player_id)] = values
    return snap


def metrics_at(match: MatchData, xt_grid: np.ndarray, period: int, t: float, scope: str,
               scope_id: str) -> dict[str, float]:  # fmt: skip
    """Every metric of a team or player at (period, t), from data up to then only."""
    return dict(snapshot(match, xt_grid, period, t).get((scope, scope_id), {}))


def _grid_times(match: MatchData, step_s: float) -> list[MatchTime]:
    times: list[MatchTime] = []
    for period in (1, 2):
        last = max([e.t for e in match.events if e.period == period]
                   + [f.t for f in match.frames if f.period == period], default=0.0)  # fmt: skip
        times += [(period, k * step_s) for k in range(int(last // step_s) + 1)]
    return times


def compute_metrics(match: MatchData, xt_grid: np.ndarray, step_s: float = 30.0,
                    extra_times: Sequence[MatchTime] = ()) -> list[MetricRow]:  # fmt: skip
    """Snapshots on the grid (`kind="grid"`) and at each extra time (`kind="moment"`)."""
    rows: list[MetricRow] = []
    plan = [(p, t, "grid") for p, t in _grid_times(match, step_s)]
    plan += [(p, t, "moment") for p, t in sorted(set(extra_times))]
    mid = match.meta.match_id
    for period, t, kind in plan:
        for (scope, scope_id), values in snapshot(match, xt_grid, period, t).items():
            rows += [MetricRow(match_id=mid, period=period, t=t, scope=scope,
                               scope_id=scope_id, name=name, value=value, kind=kind)
                     for name, value in sorted(values.items())]  # fmt: skip
    return rows
