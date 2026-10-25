"""Season baselines: each player's per-90 rates, shrunk toward his role's average.

`per90 = w · own + (1 − w) · role`, with `w = minutes / (minutes + 450)`, so a player
with one match sits near his role and one with nine full matches near his own rate.
Dispersion (variance ÷ mean of per-90 match rates, at least 1) is estimated per role,
which is steadier than per player. `expected_at` turns a rate into an expected count for
the minutes played, adjusted for possession and red cards.
"""

from collections import defaultdict

import numpy as np
from pydantic import BaseModel

from matchmind.league.season import Season
from matchmind.schemas_profile import Profiles

SHRINK_MINUTES = 450.0
DISPERSION_MIN_MINUTES = 45  # match lines used to estimate dispersion
DISPERSION_RANGE = (1.0, 10.0)
TRACKED_STATS: tuple[str, ...] = (
    "passes", "completed", "forward_passes", "progressive_passes", "key_passes", "shots",
    "shots_on_target", "dribbles", "tackles", "interceptions", "pressures", "fouls",
    "sprints", "box_touches", "goals", "assists",
)  # fmt: skip
ON_BALL = frozenset({"passes", "completed", "forward_passes", "progressive_passes",
                     "key_passes", "shots", "shots_on_target", "dribbles", "box_touches",
                     "goals", "assists"})  # fmt: skip
DEFENSIVE = frozenset({"tackles", "interceptions", "pressures", "fouls"})
MAN_DOWN_ATTACK, MAN_DOWN_DEFEND, MAN_UP_ATTACK = 0.85, 1.1, 1.1  # per player missing


class PlayerBaseline(BaseModel):
    player_id: str
    minutes: int
    per90: dict[str, float]
    dispersion: dict[str, float]
    club_possession: float = 0.5  # the club's season share of passes in its matches


class ExpectContext(BaseModel):
    possession_share: float = 0.5  # the team's share so far in this match
    season_possession: float = 0.5
    team_men: int = 11
    opp_men: int = 11


def player_baselines(season: Season, profiles: Profiles) -> dict[str, PlayerBaseline]:
    """A baseline for every player in `profiles` (those who never played get their role's)."""
    role_of = {pid: p.style.role for pid, p in profiles.players.items()}
    minutes: dict[str, int] = defaultdict(int)
    counts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    role_min: dict[str, int] = defaultdict(int)
    role_counts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    rates: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for line in season.player_lines:
        role = role_of[line.player_id]
        minutes[line.player_id] += line.minutes
        role_min[role] += line.minutes
        for stat in TRACKED_STATS:
            v = float(getattr(line, stat))
            counts[line.player_id][stat] += v
            role_counts[role][stat] += v
            if line.minutes >= DISPERSION_MIN_MINUTES:
                rates[role][stat].append(v / line.minutes * 90)
    role_rate = {role: {s: role_counts[role][s] / role_min[role] * 90 if role_min[role] else 0.0
                        for s in TRACKED_STATS} for role in set(role_of.values())}  # fmt: skip
    role_disp: dict[str, dict[str, float]] = {}
    for role in set(role_of.values()):
        role_disp[role] = {}
        for s in TRACKED_STATS:
            r = np.array(rates[role][s])
            mean = float(r.mean()) if len(r) else 0.0
            disp = float(r.var(ddof=1) / mean) if len(r) > 1 and mean > 0 else 1.0
            role_disp[role][s] = float(np.clip(disp, *DISPERSION_RANGE))
    possession = club_possession(season)
    out = {}
    for pid, role in role_of.items():
        m = minutes[pid]
        w = m / (m + SHRINK_MINUTES)
        per90 = {s: w * (counts[pid][s] / m * 90 if m else 0.0) + (1 - w) * role_rate[role][s]
                 for s in TRACKED_STATS}  # fmt: skip
        out[pid] = PlayerBaseline(player_id=pid, minutes=m, per90=per90,
                                  dispersion=dict(role_disp[role]),
                                  club_possession=possession.get(profiles.players[pid].club_id,
                                                                 0.5))  # fmt: skip
    return out


def club_possession(season: Season) -> dict[str, float]:
    """Each club's share of the passes in its own matches over the season."""
    ours: dict[str, float] = defaultdict(float)
    per_match: dict[str, float] = defaultdict(float)
    clubs_in: dict[str, set[str]] = defaultdict(set)
    for line in season.player_lines:
        ours[line.club_id] += line.passes
        per_match[line.match_id] += line.passes
        clubs_in[line.club_id].add(line.match_id)
    out = {}
    for club, matches in clubs_in.items():
        total = sum(per_match[m] for m in matches)
        out[club] = ours[club] / total if total else 0.5
    return out


def expected_at(baseline: PlayerBaseline, stat: str, minutes_played: float,
                ctx: ExpectContext) -> float:  # fmt: skip
    """Expected count of `stat` after `minutes_played`."""
    value = baseline.per90.get(stat, 0.0) * minutes_played / 90.0
    if stat in ON_BALL:
        value *= ctx.possession_share / ctx.season_possession
        value *= MAN_DOWN_ATTACK ** (11 - ctx.team_men) * MAN_UP_ATTACK ** (11 - ctx.opp_men)
    elif stat in DEFENSIVE:
        value *= (1 - ctx.possession_share) / (1 - ctx.season_possession)
        value *= MAN_DOWN_DEFEND ** (11 - ctx.team_men)
    return value
