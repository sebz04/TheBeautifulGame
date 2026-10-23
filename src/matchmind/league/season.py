"""Season history (rounds 1-9) played by the real engine: results, table, player lines.

Each round's matches run in parallel processes without frames (`simulate_with_motion`
tallies distance, speed, and sprints exactly). Rounds run in order, because cards
suspend players for the next round: a red card, or every fifth yellow, is a one-match
ban (`update_discipline`, `unavailable_for`). Milestones are short facts the narrative
agents can cite (`milestones_for`).
"""

import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from pydantic import BaseModel

from matchmind.engine.coupled import simulate_with_motion
from matchmind.engine.lineup import match_meta
from matchmind.league.clubs import derby_rival
from matchmind.league.fixtures import Fixture
from matchmind.league.league import League
from matchmind.schemas import MatchMeta
from matchmind.schemas_profile import Discipline, Profiles
from matchmind.stats.player_lines import PlayerMatchLine, player_match_lines

YELLOWS_PER_BAN = 5
APPEARANCE_STEP, CLUB_GOAL_STEP = 50, 25
STREAK_MIN, UNBEATEN_MIN = 3, 4


class MatchResult(BaseModel):
    match_id: str
    round: int
    date: str
    home_id: str
    away_id: str
    home_goals: int
    away_goals: int


class StandingRow(BaseModel):
    club_id: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_diff: int = 0
    points: int = 0


class Season(BaseModel):
    rounds: int
    results: list[MatchResult]
    standings: list[StandingRow]
    player_lines: list[PlayerMatchLine]
    milestones: dict[str, list[str]]
    discipline: dict[str, Discipline]  # after the last round: who is banned for the next one
    unavailable: dict[str, set[str]]  # match_id -> suspended players who sat it out


def match_seed(fixture: Fixture, base_seed: int = 2026) -> int:
    return base_seed * 1000 + fixture.round * 20 + int.from_bytes(fixture.match_id.encode()[-2:])


def history_meta(league: League, fixtures: list[Fixture], match_id: str,
                 unavailable: set[str] | frozenset[str] = frozenset()) -> MatchMeta:  # fmt: skip
    fixture = next(f for f in fixtures if f.match_id == match_id)
    return match_meta(league, fixture, seed=match_seed(fixture),
                      unavailable=frozenset(unavailable))  # fmt: skip


def standings(results: list[MatchResult], club_ids: list[str]) -> list[StandingRow]:
    rows = {c: StandingRow(club_id=c) for c in club_ids}
    for r in results:
        for club, gf, ga in ((r.home_id, r.home_goals, r.away_goals),
                             (r.away_id, r.away_goals, r.home_goals)):  # fmt: skip
            row = rows[club]
            row.played += 1
            row.goals_for += gf
            row.goals_against += ga
            row.won += gf > ga
            row.drawn += gf == ga
            row.lost += gf < ga
    for row in rows.values():
        row.goal_diff = row.goals_for - row.goals_against
        row.points = 3 * row.won + row.drawn
    return sorted(rows.values(), key=lambda r: (-r.points, -r.goal_diff, -r.goals_for, r.club_id))


def update_discipline(discipline: dict[str, Discipline], lines: list[PlayerMatchLine],
                      round_: int) -> dict[str, Discipline]:  # fmt: skip
    """Cards from `round_`: a red, or reaching a multiple of 5 yellows, bans the next round."""
    out = dict(discipline)
    for line in lines:
        if not (line.yellow or line.red):
            continue
        d = out[line.player_id]
        yellows = d.season_yellows + line.yellow
        banned = line.red > 0 or (yellows // YELLOWS_PER_BAN > d.season_yellows // YELLOWS_PER_BAN)
        out[line.player_id] = d.model_copy(update={
            "season_yellows": yellows,
            "career_yellows": d.career_yellows + line.yellow,
            "career_reds": d.career_reds + line.red,
            "suspended_until_round": round_ + 1 if banned else d.suspended_until_round,
        })  # fmt: skip
    return out


def unavailable_for(discipline: dict[str, Discipline], round_: int) -> set[str]:
    return {
        pid
        for pid, d in discipline.items()
        if d.suspended_until_round is not None and d.suspended_until_round >= round_
    }


_WORKER: dict[str, Any] = {}


def _init(league: League, profiles: Profiles, fixtures: list[Fixture]) -> None:
    _WORKER.update(league=league, profiles=profiles, fixtures=fixtures)


def _play(job: tuple[str, frozenset[str]]) -> tuple[MatchResult, list[PlayerMatchLine]]:
    match_id, unavailable = job
    league, profiles, fixtures = _WORKER["league"], _WORKER["profiles"], _WORKER["fixtures"]
    fixture = next(f for f in fixtures if f.match_id == match_id)
    meta = history_meta(league, fixtures, match_id, unavailable)
    data, motion = simulate_with_motion(meta, tracking=False, profiles=profiles)
    goals: dict[str, int] = defaultdict(int)
    for e in data.events:
        if e.type == "goal":
            goals[e.team_id] += 1
    result = MatchResult(
        match_id=match_id,
        round=fixture.round,
        date=fixture.date,
        home_id=fixture.home_id,
        away_id=fixture.away_id,
        home_goals=goals[fixture.home_id],
        away_goals=goals[fixture.away_id],
    )
    return result, player_match_lines(data, motion, round_=fixture.round)


def simulate_history(
    league: League,
    profiles: Profiles,
    fixtures: list[Fixture],
    rounds: int = 9,
    workers: int | None = None,
) -> Season:
    """Rounds 1..`rounds`, deterministic (each match's seed comes from its fixture)."""
    workers = workers or os.cpu_count() or 1
    discipline = {pid: p.discipline for pid, p in profiles.players.items()}
    results: list[MatchResult] = []
    lines: list[PlayerMatchLine] = []
    sat_out: dict[str, set[str]] = {}
    with ProcessPoolExecutor(workers, initializer=_init,
                             initargs=(league, profiles, fixtures)) as pool:  # fmt: skip
        for round_ in range(1, rounds + 1):
            banned = unavailable_for(discipline, round_)
            todo = [f for f in fixtures if f.round == round_]
            jobs = []
            for f in todo:
                out = frozenset(p.player_id for club in (f.home_id, f.away_id)
                                for p in league.squads[club] if p.player_id in banned)  # fmt: skip
                sat_out[f.match_id] = set(out)
                jobs.append((f.match_id, out))
            round_lines: list[PlayerMatchLine] = []
            for result, match_lines in pool.map(_play, jobs):
                results.append(result)
                round_lines += match_lines
            lines += round_lines
            discipline = update_discipline(discipline, round_lines, round_)
    table = standings(results, [c.club_id for c in league.clubs])
    season = Season(rounds=rounds, results=results, standings=table, player_lines=lines,
                    milestones={}, discipline=discipline, unavailable=sat_out)  # fmt: skip
    season.milestones = _milestones(season, league, profiles)
    return season


def _milestones(season: Season, league: League, profiles: Profiles) -> dict[str, list[str]]:
    names = {c.club_id: c.name for c in league.clubs}
    by_match = {r.match_id: r for r in season.results}
    out: dict[str, list[str]] = defaultdict(list)
    apps: dict[str, int] = defaultdict(int)
    goals: dict[str, int] = defaultdict(int)
    clean: dict[str, int] = defaultdict(int)
    for line in season.player_lines:
        r = by_match[line.match_id]
        opp = r.away_id if line.club_id == r.home_id else r.home_id
        vs = f"vs {names[opp]} (round {line.round})"
        prof = profiles.players[line.player_id]
        origin_apps = prof.origin.club_apps if prof.origin else 0
        origin_goals = prof.origin.club_goals if prof.origin else 0
        if line.minutes > 0:
            apps[line.player_id] += 1
            total = origin_apps + apps[line.player_id]
            if total % APPEARANCE_STEP == 0:
                out[line.player_id].append(f"{total}th appearance for {names[line.club_id]} {vs}")
        if line.goals:
            if goals[line.player_id] == 0:
                out[line.player_id].append(f"first league goal of the season {vs}")
            if line.goals >= 3:
                out[line.player_id].append(f"hat-trick {vs}")
            before = origin_goals + goals[line.player_id]
            goals[line.player_id] += line.goals
            after = origin_goals + goals[line.player_id]
            if after // CLUB_GOAL_STEP > before // CLUB_GOAL_STEP:
                n = after // CLUB_GOAL_STEP * CLUB_GOAL_STEP
                out[line.player_id].append(f"{n}th goal for {names[line.club_id]} {vs}")
        if line.red:
            out[line.player_id].append(f"sent off {vs}")
        conceded = r.away_goals if line.club_id == r.home_id else r.home_goals
        if prof.style.position == "GK" and line.minutes >= 60 and conceded == 0:
            clean[line.player_id] += 1
    for pid, n in clean.items():
        if n >= 2:
            out[pid].append(f"{n} clean sheets this season")
    for pid, d in season.discipline.items():
        if d.suspended_until_round is not None and d.suspended_until_round > season.rounds:
            out[pid].append(f"suspended for round {season.rounds + 1}")
    _club_milestones(season, names, out)
    return dict(out)


def _club_milestones(season: Season, names: dict[str, str], out: dict[str, list[str]]) -> None:
    form: dict[str, list[str]] = defaultdict(list)
    for r in sorted(season.results, key=lambda r: r.round):
        for club, gf, ga in ((r.home_id, r.home_goals, r.away_goals),
                             (r.away_id, r.away_goals, r.home_goals)):  # fmt: skip
            form[club].append("W" if gf > ga else "D" if gf == ga else "L")
            opp = r.away_id if club == r.home_id else r.home_id
            if gf > ga and derby_rival(club) == opp:
                out[club].append(f"beat {names[opp]} in the derby (round {r.round})")
    for club, f in form.items():
        streak = len(f) - len("".join(f).rstrip("W"))
        unbeaten = len(f) - len("".join(f).rstrip("WD"))
        losses = len(f) - len("".join(f).rstrip("L"))
        if streak >= STREAK_MIN:
            out[club].append(f"won the last {streak}")
        elif unbeaten >= UNBEATEN_MIN:
            out[club].append(f"unbeaten in {unbeaten}")
        if losses >= STREAK_MIN:
            out[club].append(f"lost the last {losses}")
    after = f"after round {season.rounds}"
    out[season.standings[0].club_id].append(f"top of the table {after}")
    out[season.standings[-1].club_id].append(f"bottom of the table {after}")


def milestones_for(season: Season, entity_id: str) -> list[str]:
    """Milestones for a player or a club (empty if none)."""
    return list(season.milestones.get(entity_id, []))
