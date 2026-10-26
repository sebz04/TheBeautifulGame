"""Live player discrepancies: counts so far against what the season baseline expects.

A count is tested with a negative binomial of mean `expected` and variance `dispersion ×
expected` (Poisson when the dispersion is about 1). A deviation is flagged only when
p < 0.01 and the player has played at least 30 minutes; an "under" also needs at least
5 expected, an "over" at least 3 observed. `deviation_moments` checks every 5 minutes,
keeps the 3 strongest new flags per check (by −log p), and flags each player once per
stat group (`GROUP_OF`: passing and shooting stats move together). Expectations use the
club's season possession share from the baseline.
"""

import math
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from matchmind.engine.coupled import Motion
from matchmind.schemas import MatchData, Moment
from matchmind.stats.baselines import (
    TRACKED_STATS,
    ExpectContext,
    PlayerBaseline,
    expected_at,
)
from matchmind.stats.player_lines import player_match_lines
from matchmind.stats.speed import player_motion

__all__ = ["TRACKED_STATS", "Deviation", "ExpectContext", "assess", "detect_deviations",
           "deviation_moments", "expected_so_far", "tail_p"]  # fmt: skip

P_MAX = 0.01
MIN_MINUTES = 30.0
MIN_EXPECTED_UNDER = 5.0
MIN_OBSERVED_OVER = 3
POISSON_DISPERSION = 1.05
CHECK_EVERY_S = 300.0
# Stats that move together count as one: a player is flagged once per group.
GROUP_OF: dict[str, str] = {
    **dict.fromkeys(("passes", "completed", "forward_passes", "progressive_passes"), "passing"),
    **dict.fromkeys(("shots", "shots_on_target", "goals"), "shooting"),
}
TOP_PER_CHECK = 3
MatchTime = tuple[int, float]
Direction = Literal["under", "over"]


class Deviation(BaseModel):
    player_id: str
    stat: str
    observed: int
    expected: float
    p_value: float
    direction: Direction
    baseline_per90: float
    minutes_played: float


def _log_pmf(k: int, mean: float, dispersion: float) -> float:
    if dispersion <= POISSON_DISPERSION:
        return k * math.log(mean) - mean - math.lgamma(k + 1)
    r = mean / (dispersion - 1.0)  # NB: variance = mean · dispersion
    p = 1.0 / dispersion
    return (math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
            + r * math.log(p) + k * math.log(1.0 - p))  # fmt: skip


def tail_p(observed: int, mean: float, dispersion: float, direction: Direction) -> float:
    """P(X ≤ observed) for "under", P(X ≥ observed) for "over"."""
    if mean <= 0:
        return 1.0
    below = sum(math.exp(_log_pmf(k, mean, dispersion)) for k in range(observed + 1))
    if direction == "under":
        return min(below, 1.0)
    return min(max(1.0 - below + math.exp(_log_pmf(observed, mean, dispersion)), 0.0), 1.0)


def assess(baseline: PlayerBaseline, stat: str, observed: int, minutes_played: float,
           ctx: ExpectContext) -> Deviation | None:  # fmt: skip
    if minutes_played < MIN_MINUTES:
        return None
    expected = expected_at(baseline, stat, minutes_played, ctx)
    direction: Direction = "under" if observed < expected else "over"
    if direction == "under" and expected < MIN_EXPECTED_UNDER:
        return None
    if direction == "over" and observed < MIN_OBSERVED_OVER:
        return None
    p = tail_p(observed, expected, baseline.dispersion.get(stat, 1.0), direction)
    if p >= P_MAX:
        return None
    return Deviation(player_id=baseline.player_id, stat=stat, observed=observed,
                     expected=round(expected, 3), p_value=p, direction=direction,
                     baseline_per90=round(baseline.per90.get(stat, 0.0), 3),
                     minutes_played=round(minutes_played, 1))  # fmt: skip


def _clock(match: MatchData, period: int, t: float) -> float:
    """Minutes since kickoff (first-half added time included)."""
    first = 45.0 + match.meta.added_time_s[0] / 60.0
    return t / 60.0 if period == 1 else first + t / 60.0


def minutes_played(match: MatchData, t_to: MatchTime) -> dict[str, float]:
    now = _clock(match, *t_to)
    on: dict[str, float] = {p.player_id: 0.0 for p in match.meta.home_squad[:11]
                            + match.meta.away_squad[:11]}  # fmt: skip
    played: dict[str, float] = {}
    for e in match.events:
        if (e.period, e.t) > t_to:
            break
        at = _clock(match, e.period, e.t)
        leaving = e.type == "sub" or (e.type == "card" and e.extras.get("card") == "red")
        if leaving and e.player_id in on:
            played[e.player_id] = played.get(e.player_id, 0.0) + at - on.pop(e.player_id)
        if e.type == "sub" and e.receiver_id is not None:
            on[e.receiver_id] = at
    for pid, start in on.items():
        played[pid] = played.get(pid, 0.0) + now - start
    return played


def _context(match: MatchData, team: str, t_to: MatchTime, season_share: float) -> ExpectContext:
    upto = [e for e in match.events if (e.period, e.t) <= t_to]
    passes = [e.team_id for e in upto if e.type == "pass"]
    share = passes.count(team) / len(passes) if passes else 0.5
    reds = [e.team_id for e in upto if e.type == "card" and e.extras.get("card") == "red"]
    return ExpectContext(possession_share=min(max(share, 0.2), 0.8),
                         season_possession=min(max(season_share, 0.2), 0.8),
                         team_men=11 - reds.count(team),
                         opp_men=11 - (len(reds) - reds.count(team)))  # fmt: skip


def expected_so_far(match: MatchData, baseline: PlayerBaseline, t: MatchTime,
                    stats: Sequence[str] = TRACKED_STATS) -> dict[str, float]:  # fmt: skip
    """What the season baseline expects of the player by (period, t): the API's
    "vs season average", with the same minutes and possession context as the flags."""
    played = minutes_played(match, t).get(baseline.player_id, 0.0)
    club = next(p.club_id for p in match.meta.home_squad + match.meta.away_squad
                if p.player_id == baseline.player_id)  # fmt: skip
    ctx = _context(match, club, t, baseline.club_possession)
    return {s: round(expected_at(baseline, s, played, ctx), 3) for s in stats}


def detect_deviations(match: MatchData, baselines: dict[str, PlayerBaseline], t: MatchTime,
                      stats: Sequence[str] = TRACKED_STATS) -> list[Deviation]:  # fmt: skip
    """Every flagged deviation at (period, t), strongest first. Sprints need frames."""
    played = minutes_played(match, t)
    stats = [s for s in stats if s != "sprints" or match.frames]
    motion = {pid: (player_motion(match.frames, pid, t) if match.frames else Motion(minutes=m))
              for pid, m in played.items() if m > 0}  # fmt: skip
    upto = match.model_copy(update={"events": [e for e in match.events if (e.period, e.t) <= t]})
    club = {p.player_id: p.club_id for p in match.meta.home_squad + match.meta.away_squad}
    found = []
    for line in player_match_lines(upto, motion, round_=0):
        base = baselines.get(line.player_id)
        if base is None:
            continue
        ctx = _context(match, club[line.player_id], t, base.club_possession)
        for stat in stats:
            dev = assess(base, stat, int(getattr(line, stat)), played[line.player_id], ctx)
            if dev is not None:
                found.append(dev)
    return sorted(found, key=lambda d: d.p_value)


def deviation_moments(
    match: MatchData, baselines: dict[str, PlayerBaseline], stats: Sequence[str] = TRACKED_STATS
) -> list[tuple[Moment, Deviation]]:
    """Checks every 5 minutes; each player-stat is flagged at most once."""
    club = {p.player_id: p.club_id for p in match.meta.home_squad + match.meta.away_squad}
    seen: set[tuple[str, str]] = set()  # (player, stat group)
    out: list[tuple[Moment, Deviation]] = []
    for period in (1, 2):
        last = max((e.t for e in match.events if e.period == period), default=0.0)
        t = CHECK_EVERY_S
        while t <= last:
            fresh: list[Deviation] = []
            for d in detect_deviations(match, baselines, (period, t), stats):
                key = (d.player_id, GROUP_OF.get(d.stat, d.stat))
                if key not in seen and len(fresh) < TOP_PER_CHECK:
                    seen.add(key)
                    fresh.append(d)
            for d in fresh:
                m = Moment(moment_id=f"{match.meta.match_id}-d{len(out):03d}",
                           match_id=match.meta.match_id, period=period, t_start=t, t_end=t,
                           kind="player_deviation", level="player", team_id=club[d.player_id],
                           player_id=d.player_id, trigger_metric=d.stat,
                           trigger_value=float(d.observed), event_ids=[])  # fmt: skip
                out.append((m, d))
            t += CHECK_EVERY_S
    return out
