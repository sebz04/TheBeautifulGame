import time
from collections import Counter
from functools import cache

import pytest

from matchmind.engine.coupled import simulate_with_motion
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles
from matchmind.league.season import (
    MatchResult,
    Season,
    milestones_for,
    simulate_history,
    standings,
    unavailable_for,
    update_discipline,
)
from matchmind.schemas_profile import Discipline
from matchmind.stats.player_lines import PlayerMatchLine, player_match_lines


@cache
def _setup():  # type: ignore[no-untyped-def]
    league = build_league()
    return league, build_profiles(league, seed=2026), build_fixtures(league, seed=2026)


@cache
def _season(rounds: int = 2) -> Season:
    league, profiles, fixtures = _setup()
    return simulate_history(league, profiles, fixtures, rounds=rounds)


def test_history_deterministic() -> None:
    league, profiles, fixtures = _setup()
    again = simulate_history(league, profiles, fixtures, rounds=1)
    first = _season(2)
    assert again.results == [r for r in first.results if r.round == 1]
    assert again.player_lines == [line for line in first.player_lines if line.round == 1]


def test_standings_match_results() -> None:
    season = _season(2)
    assert len(season.results) == 20 and {r.round for r in season.results} == {1, 2}
    table = {row.club_id: row for row in season.standings}
    assert len(table) == 20
    for club, row in table.items():
        mine = [r for r in season.results if club in (r.home_id, r.away_id)]
        assert row.played == len(mine) == 2
        assert row.won + row.drawn + row.lost == row.played
        assert row.points == 3 * row.won + row.drawn
        gf = sum(r.home_goals if r.home_id == club else r.away_goals for r in mine)
        assert row.goals_for == gf and row.goal_diff == row.goals_for - row.goals_against
    keys = [(-r.points, -r.goal_diff, -r.goals_for, r.club_id) for r in season.standings]
    assert keys == sorted(keys)


def test_lines_agree_with_their_match() -> None:
    league, profiles, fixtures = _setup()
    season = _season(2)
    result = season.results[0]
    lines = [line for line in season.player_lines if line.match_id == result.match_id]
    goals = Counter(line.club_id for line in lines for _ in range(line.goals))
    own = result.home_goals - goals[result.home_id], result.away_goals - goals[result.away_id]
    assert min(own) >= 0  # the rest are own goals
    assert sum(1 for line in lines if line.minutes > 0) >= 22
    # Re-simulating the match reproduces its lines exactly.
    from matchmind.league.season import history_meta

    meta = history_meta(league, fixtures, result.match_id, season.unavailable[result.match_id])
    data, motion = simulate_with_motion(meta, tracking=False, profiles=profiles)
    assert player_match_lines(data, motion, round_=result.round) == lines


def _line(pid: str, round_: int, yellow: int = 0, red: int = 0, goals: int = 0) -> PlayerMatchLine:
    return PlayerMatchLine(match_id=f"r{round_:02d}-a-v-b", round=round_, player_id=pid,
                           club_id="a", minutes=90, yellow=yellow, red=red,
                           goals=goals)  # fmt: skip


def test_suspensions_from_cards() -> None:
    disc = {"p1": Discipline(career_yellows=10, career_reds=1, season_yellows=4),
            "p2": Discipline(career_yellows=0, career_reds=0)}  # fmt: skip
    disc = update_discipline(disc, [_line("p1", 3, yellow=1), _line("p2", 3, red=1)], 3)
    assert disc["p1"].season_yellows == 5 and disc["p1"].suspended_until_round == 4
    assert disc["p2"].suspended_until_round == 4 and disc["p2"].career_reds == 1
    assert unavailable_for(disc, 4) == {"p1", "p2"}
    assert unavailable_for(disc, 5) == set()


def test_suspended_players_sit_out() -> None:
    season = _season(2)
    for match_id, out in season.unavailable.items():
        played = {line.player_id for line in season.player_lines if line.match_id == match_id}
        assert not out & played


def test_milestones() -> None:
    season = _season(2)
    scorers = {line.player_id for line in season.player_lines if line.goals}
    assert scorers
    for pid in scorers:
        assert any("goal" in m for m in milestones_for(season, pid)), pid
    leader = season.standings[0].club_id
    assert any("top of the table" in m for m in milestones_for(season, leader))
    assert milestones_for(season, "nobody") == []


def test_result_model() -> None:
    r = MatchResult(match_id="r01-a-v-b", round=1, date="2026-08-15", home_id="a",
                    away_id="b", home_goals=2, away_goals=1)  # fmt: skip
    rows = {row.club_id: row for row in standings([r], ["a", "b"])}
    assert rows["a"].points == 3 and rows["b"].points == 0 and rows["b"].lost == 1


@pytest.mark.slow
def test_runtime_budget() -> None:
    league, profiles, fixtures = _setup()
    start = time.perf_counter()
    season = simulate_history(league, profiles, fixtures, rounds=9)
    assert len(season.results) == 90
    assert time.perf_counter() - start < 30 * 60
