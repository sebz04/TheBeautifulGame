"""Key moments: rule triggers over a match's events (and frames, when there are any).

- goal, red_card (player): the event itself.
- big_chance (player): a shot with xG above 0.25.
- momentum_swing (game): the momentum `diff` changes sign within 5 min by more than 0.08.
- pressing_collapse (team): a team's PPDA in the 10 min after a 5-minute mark is more
  than 60% above the 10 min before it, when it had been pressing (PPDA ≤ 12) and the
  opponent made at least 10 passes after the mark.
- formation_shift (team): the nearest formation template (`classify_formation`) of a
  team's mean shape over the last 3 min changes and holds for 3 min (frames only).
- offside_trap (team, credited to the defenders): 3+ offsides against one team in 20 min.
- corner_pressure (team): 3+ corners for one team within 5 min.

Moments of the same kind and team less than 60 s apart merge (`merge_moments`); ids are
`{match_id}-mNNN` in time order. Windows never cross half time.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence

import numpy as np

from matchmind.engine.lineup import FORMATION_LINES
from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH, attacks_right
from matchmind.schemas import Event, Level, MatchData, Moment, MomentKind
from matchmind.stats.team import momentum_series, ppda

BIG_CHANCE_XG = 0.25
SWING_WINDOW_S, SWING_DELTA = 300.0, 0.08
PPDA_WINDOW_S, PPDA_STEP_S, PPDA_RISE, PPDA_MIN_PASSES = 600.0, 300.0, 1.6, 10
PPDA_PRESSING_MAX = 12.0  # only a team that was pressing (PPDA this low or lower) collapses
SHIFT_WINDOW_S, SHIFT_HOLD_S, SHIFT_SAMPLE_S = 180.0, 180.0, 30.0
OFFSIDE_WINDOW_S, OFFSIDE_COUNT = 1200.0, 3
CORNER_WINDOW_S, CORNER_COUNT = 300.0, 3
MERGE_S = 60.0
HALF_S = 2700.0


def _line_counts(depths: np.ndarray, k: int) -> np.ndarray:
    """Players per line when sorted depths are split into k contiguous lines with the least
    total within-line squared spread (exact, by dynamic programming over the 7-10 players)."""
    d = np.sort(np.asarray(depths, dtype=float))
    n = len(d)

    def sse(i: int, j: int) -> float:
        seg = d[i:j]
        return float(((seg - seg.mean()) ** 2).sum())

    best = np.full((k + 1, n + 1), np.inf)
    cut = np.zeros((k + 1, n + 1), dtype=int)
    best[0, 0] = 0.0
    for lines in range(1, k + 1):
        for j in range(lines, n + 1):
            for i in range(lines - 1, j):
                c = best[lines - 1, i] + sse(i, j)
                if c < best[lines, j]:
                    best[lines, j], cut[lines, j] = c, i
    counts, j = [], n
    for lines in range(k, 0, -1):
        i = int(cut[lines, j])
        counts.append(j - i)
        j = i
    return np.array(counts[::-1])


def classify_formation(outfield: np.ndarray) -> str:
    """Nearest formation by players per line: each template's lines (e.g. 4-2-3-1 has 4)
    against the team's depths split into that many lines (`_line_counts`)."""
    depths = np.sort(np.asarray(outfield, dtype=float)[:, 0])
    scale = 10 / len(depths)  # compare as if with 10 outfield players

    def cost(formation: str) -> tuple[float, int, str]:
        lines = np.array([int(n) for n in formation.split("-")])
        counts = _line_counts(depths, len(lines)) * scale
        return float(np.abs(counts - lines).sum()), len(lines), formation

    return min(FORMATION_LINES, key=cost)


def _moment(kind: MomentKind, level: Level, period: int, t0: float, t1: float,
            team: str | None, player: str | None, metric: str, value: float,
            events: Iterable[str]) -> Moment:  # fmt: skip
    return Moment(moment_id="", match_id="", period=period, t_start=t0, t_end=t1,
                  kind=kind, level=level, team_id=team, player_id=player, trigger_metric=metric,
                  trigger_value=float(value), event_ids=list(events))  # fmt: skip


def merge_moments(moments: Sequence[Moment], gap_s: float = MERGE_S) -> list[Moment]:
    """Join same-kind, same-team moments in the same half less than `gap_s` apart."""
    out: list[Moment] = []
    last: dict[tuple[str, str | None, int], int] = {}
    for m in sorted(moments, key=lambda m: (m.period, m.t_start)):
        key = (m.kind, m.team_id, m.period)
        i = last.get(key)
        if i is not None and m.t_start - out[i].t_end < gap_s:
            prev = out[i]
            ids = prev.event_ids + [e for e in m.event_ids if e not in prev.event_ids]
            out[i] = prev.model_copy(update={
                "t_end": max(prev.t_end, m.t_end), "event_ids": ids,
                "trigger_value": max(prev.trigger_value, m.trigger_value)})  # fmt: skip
            continue
        last[key] = len(out)
        out.append(m)
    return out


def _events_moments(events: Sequence[Event], home: str, away: str) -> list[Moment]:
    out = []
    other = {home: away, away: home}
    for e in events:
        if e.type == "goal":
            out.append(_moment("goal", "player", e.period, e.t, e.t, e.team_id, e.player_id,
                               "goal", 1.0, [e.event_id]))  # fmt: skip
        elif e.type == "card" and e.extras.get("card") == "red":
            out.append(_moment("red_card", "player", e.period, e.t, e.t, e.team_id, e.player_id,
                               "card", 1.0, [e.event_id]))  # fmt: skip
        elif e.type == "shot" and float(e.extras.get("xg", 0.0)) > BIG_CHANCE_XG:
            out.append(_moment("big_chance", "player", e.period, e.t, e.t, e.team_id,
                               e.player_id, "xg", float(e.extras["xg"]), [e.event_id]))  # fmt: skip
    # Offsides against a team (credited to the defenders) and corners for a team.
    caught: dict[str, list[Event]] = defaultdict(list)
    corners: dict[str, list[Event]] = defaultdict(list)
    for e in events:
        if e.type == "offside":
            caught[e.team_id].append(e)
        elif e.type == "out" and e.extras.get("restart") == "corner":
            corners[other[e.team_id]].append(e)
    for team, evs in caught.items():
        out += _bursts(evs, OFFSIDE_WINDOW_S, OFFSIDE_COUNT, "offside_trap", other[team],
                       "offsides_20min")  # fmt: skip
    for team, evs in corners.items():
        out += _bursts(evs, CORNER_WINDOW_S, CORNER_COUNT, "corner_pressure", team, "corners_5min")
    return out


def _bursts(evs: list[Event], window: float, count: int, kind: MomentKind, team: str,
            metric: str) -> list[Moment]:  # fmt: skip
    """A moment each time `count` events fall within `window` seconds of the same half."""
    out = []
    evs = sorted(evs, key=lambda e: (e.period, e.t))
    for i, e in enumerate(evs):
        recent = [x for x in evs[: i + 1] if x.period == e.period and e.t - x.t <= window]
        if len(recent) >= count:
            out.append(_moment(kind, "team", e.period, recent[0].t, e.t, team, None, metric,
                               len(recent), [x.event_id for x in recent]))  # fmt: skip
    return out


def _momentum_swings(match: MatchData, grid: np.ndarray) -> list[Moment]:
    home, away = match.meta.home.club_id, match.meta.away.club_id
    series = momentum_series(match.events, grid, home_id=home, window_s=SWING_WINDOW_S)
    out = []
    by_period: dict[int, list] = defaultdict(list)  # type: ignore[type-arg]
    for p in series.points:
        by_period[p.period].append(p)
    for period, pts in by_period.items():
        lag = round(SWING_WINDOW_S / series.step_s)
        for before, now in zip(pts, pts[lag:], strict=False):
            if before.diff * now.diff < 0 and abs(now.diff - before.diff) > SWING_DELTA:
                team = home if now.diff > 0 else away
                out.append(_moment("momentum_swing", "game", period, before.t, now.t, team, None,
                                   "momentum_diff", abs(now.diff - before.diff), []))  # fmt: skip
    return out


def _pressing_collapses(match: MatchData) -> list[Moment]:
    """PPDA in the 10 minutes after each 5-minute mark against the 10 minutes before it."""
    home, away = match.meta.home.club_id, match.meta.away.club_id
    out = []
    for period in (1, 2):
        last = max((e.t for e in match.events if e.period == period), default=0.0)
        marks = np.arange(PPDA_WINDOW_S, last - PPDA_WINDOW_S / 2, PPDA_STEP_S)
        for team, opp in ((home, away), (away, home)):
            for mark in marks:
                before = ((period, mark - PPDA_WINDOW_S), (period, mark - 1e-6))
                after = ((period, mark), (period, mark + PPDA_WINDOW_S - 1e-6))
                passes = sum(e.type == "pass" and e.team_id == opp
                             and after[0] <= (e.period, e.t) <= after[1]
                             for e in match.events)  # fmt: skip
                prev = ppda(match.events, team, home, *before)
                now = ppda(match.events, team, home, *after)
                if prev is None or prev > PPDA_PRESSING_MAX or passes < PPDA_MIN_PASSES:
                    continue
                if now is None or now > PPDA_RISE * prev:
                    ratio = now / prev if now is not None else float(passes)
                    t0 = float(mark)
                    out.append(_moment("pressing_collapse", "team", period, t0, t0, team, None,
                                       "ppda_ratio", round(ratio, 3), []))  # fmt: skip
    return out


def _formation_shifts(match: MatchData) -> list[Moment]:
    if not match.frames:
        return []
    home = match.meta.home.club_id
    out = []
    for team in (home, match.meta.away.club_id):
        keepers = {p.player_id for p in match.meta.home_squad + match.meta.away_squad
                   if p.position == "GK"}  # fmt: skip
        for period in (1, 2):
            right = attacks_right(team == home, period)
            samples: list[tuple[float, np.ndarray]] = []
            for f in match.frames:
                if f.period != period or round(f.t * 10) % 10:
                    continue  # one sample per second
                xy = np.array([(p.x, p.y) for p in f.players
                               if p.team_id == team and p.player_id not in keepers])  # fmt: skip
                if len(xy) < 7:
                    continue
                if not right:
                    xy = np.array([PITCH_LENGTH, PITCH_WIDTH]) - xy
                samples.append((f.t, xy[np.argsort(xy[:, 0])]))
            labels: list[tuple[float, str]] = []
            t = SHIFT_WINDOW_S
            last = samples[-1][0] if samples else 0.0
            while t <= last:
                window = [xy for ts, xy in samples if t - SHIFT_WINDOW_S < ts <= t
                          and len(xy) == len(samples[-1][1])]  # fmt: skip
                if window:
                    labels.append((t, classify_formation(np.mean(window, axis=0))))
                t += SHIFT_SAMPLE_S
            hold = round(SHIFT_HOLD_S / SHIFT_SAMPLE_S)
            for i in range(1, len(labels) - hold + 1):
                prev, now = labels[i - 1][1], labels[i][1]
                if prev != now and all(lab == now for _, lab in labels[i : i + hold]):
                    t0 = labels[i][0] - SHIFT_WINDOW_S / 2
                    out.append(_moment("formation_shift", "team", period, max(t0, 0.0),
                                       labels[i][0], team, None, f"formation:{prev}->{now}",
                                       float(sum(FORMATION_LINES[now])), []))  # fmt: skip
    return out


def detect_moments(match: MatchData, xt_grid: np.ndarray) -> list[Moment]:
    home, away = match.meta.home.club_id, match.meta.away.club_id
    found = _events_moments(match.events, home, away)
    found += _momentum_swings(match, xt_grid)
    found += _pressing_collapses(match)
    found += _formation_shifts(match)
    merged = merge_moments(found)
    merged.sort(key=lambda m: (m.period, m.t_start, m.kind))
    mid = match.meta.match_id
    return [m.model_copy(update={"moment_id": f"{mid}-m{n:03d}", "match_id": mid})
            for n, m in enumerate(merged)]  # fmt: skip
