"""Attributes really change the simulated data (TASK-10.5; `slow`, run nightly).

Each test plays the same fixture over many seeds with two versions of the home club's
profiles, which differ only in the attribute under test, and compares home-team stats.
Matches run in parallel processes without frames.
"""

from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from typing import Any

import numpy as np
import pytest

from matchmind.engine.coupled import simulate_with_motion
from matchmind.engine.lineup import match_meta
from matchmind.engine.modifiers import STORYLINE_CAP, SUBTLE_CAP, MatchContext, Modifiers
from matchmind.engine.pitch import attacks_right
from matchmind.engine.validate import _event_stats
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles
from matchmind.schemas_profile import PlayerProfile, Profiles
from matchmind.stats.player_lines import player_match_lines

pytestmark = pytest.mark.slow
SEEDS = range(1, 25)


@cache
def _base() -> tuple[Any, Profiles, list[Any]]:
    league = build_league()
    return league, build_profiles(league, seed=2026), build_fixtures(league, seed=2026)


def _edit_players(profiles: Profiles, club: str, positions: set[str] | None,
                  edit: Callable[[PlayerProfile], PlayerProfile]) -> Profiles:  # fmt: skip
    players = {pid: (edit(p) if p.club_id == club and (positions is None or p.style.position
                                                       in positions) else p)
               for pid, p in profiles.players.items()}  # fmt: skip
    return profiles.model_copy(update={"players": players})


def _personality(**kw: float) -> Callable[[PlayerProfile], PlayerProfile]:
    return lambda p: p.model_copy(update={"personality": p.personality.model_copy(update=kw)})


def _style(**kw: float) -> Callable[[PlayerProfile], PlayerProfile]:
    return lambda p: p.model_copy(update={"style": p.style.model_copy(update=kw)})


def _tactics(profiles: Profiles, club: str, **kw: float) -> Profiles:
    c = profiles.clubs[club]
    c = c.model_copy(update={"tactical_identity": c.tactical_identity.model_copy(update=kw)})
    return profiles.model_copy(update={"clubs": {**profiles.clubs, club: c}})


def _variant(name: str, profiles: Profiles, home: str, away: str) -> Profiles:
    v = {
        "aggressive": lambda: _edit_players(profiles, home, None, _personality(aggression=0.95)),
        "calm": lambda: _edit_players(profiles, home, None, _personality(aggression=0.05)),
        "press_high": lambda: _tactics(profiles, home, press_intensity=0.95),
        "press_low": lambda: _tactics(profiles, home, press_intensity=0.05),
        "risky": lambda: _edit_players(profiles, home, None, _style(risk_tolerance=0.95)),
        "safe": lambda: _edit_players(profiles, home, None, _style(risk_tolerance=0.05)),
        "direct_vs_high": lambda: _tactics(_tactics(profiles, home, directness=0.95, tempo=0.9),
                                           away, line_height=0.95),
        "patient_vs_deep": lambda: _tactics(_tactics(profiles, home, directness=0.05, tempo=0.1),
                                            away, line_height=0.05),
        "disciplined": lambda: _edit_players(
            profiles, home, {"FW"},
            lambda p: _style(tactical_discipline=0.95)(_personality(composure=0.95)(p))),
        "impulsive": lambda: _edit_players(
            profiles, home, {"FW"},
            lambda p: _style(tactical_discipline=0.05)(_personality(composure=0.05)(p))),
        "returning": lambda: _edit_players(profiles, home, None, lambda p: p.model_copy(
            update={"status": p.status.model_copy(update={"injury": "returning"})})),
        "fit": lambda: _edit_players(profiles, home, None, lambda p: p.model_copy(
            update={"status": p.status.model_copy(update={"injury": "fit"})})),
        "close_knit": lambda: _edit_players(profiles, home, None, lambda p: p.model_copy(
            update={"origin": p.origin.model_copy(update={"joined_year": 2018}) if p.origin
                    else None})),
        "new_faces": lambda: _edit_players(profiles, home, None, lambda p: p.model_copy(
            update={"origin": p.origin.model_copy(update={"joined_year": 2026, "kind": "signed"})
                    if p.origin else None})),
        "none": lambda: profiles,
    }  # fmt: skip
    return v[name]()


def _play(job: tuple[str, int, int]) -> dict[str, float]:
    """Home-team stats for one seed under one variant."""
    name, seed, fixture_idx = job
    league, profiles, fixtures = _base()
    fixture = fixtures[fixture_idx]
    profiles = _variant(name, profiles, fixture.home_id, fixture.away_id)
    meta = match_meta(league, fixture, seed=seed)
    data, motion = simulate_with_motion(meta, tracking=False, profiles=profiles)
    home = meta.home.club_id
    ev = _event_stats(data)[home]
    lines = [line for line in player_match_lines(data, motion, round_=1) if line.club_id == home]
    outfield = [line for line in lines if line.player_id != meta.home_squad[0].player_id]
    goals = {t: sum(e.type == "goal" and e.team_id == t for e in data.events)
             for t in (home, meta.away.club_id)}  # fmt: skip
    return {
        "fouls": ev["fouls"], "ppda": ev["ppda"], "offsides": ev["offsides"],
        "completion": ev["pass_completion"], "passes": ev["passes"],
        "progressive": sum(line.progressive_passes for line in lines),
        "distance": float(np.mean([line.distance_km / max(line.minutes, 1) * 90
                                   for line in outfield if line.minutes >= 60])),
        "home_win": float(goals[home] > goals[meta.away.club_id]),
        "attacks_right_p1": float(attacks_right(True, 1)),
    }  # fmt: skip


def _compare(a: str, b: str, seeds: range = SEEDS, fixture_idx: int = 0) -> tuple[dict, dict]:  # type: ignore[type-arg]
    jobs = [(name, s, fixture_idx) for name in (a, b) for s in seeds]
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(_play, jobs))
    n = len(seeds)

    def mean(rs: list[dict[str, float]]) -> dict[str, float]:
        return {k: float(np.mean([r[k] for r in rs])) for k in rs[0]}

    return mean(results[:n]), mean(results[n:])


def test_aggressive_teams_foul_more() -> None:
    hi, lo = _compare("aggressive", "calm")
    assert hi["fouls"] > lo["fouls"]


def test_high_press_gives_lower_ppda() -> None:
    hi, lo = _compare("press_high", "press_low")
    assert hi["ppda"] < lo["ppda"]


def test_chemistry_raises_completion() -> None:
    knit, new = _compare("close_knit", "new_faces")
    assert knit["completion"] > new["completion"]


def test_returning_players_cover_less_ground() -> None:
    back, fit = _compare("returning", "fit")
    assert back["distance"] < fit["distance"]


def test_risk_tolerance_trades_completion_for_progress() -> None:
    risky, safe = _compare("risky", "safe")
    assert risky["progressive"] > safe["progressive"]
    assert risky["completion"] < safe["completion"]


def test_offsides_follow_tactics() -> None:
    direct, patient = _compare("direct_vs_high", "patient_vs_deep")
    assert direct["offsides"] > patient["offsides"]


def test_disciplined_strikers_are_caught_offside_less() -> None:
    calm, rash = _compare("disciplined", "impulsive", seeds=range(1, 61))
    assert calm["offsides"] < rash["offsides"]


def test_home_win_rate() -> None:
    jobs = [("none", s, f) for f in range(0, 380, 19) for s in (1, 2, 3, 4, 5, 6)]
    with ProcessPoolExecutor() as pool:
        wins = [r["home_win"] for r in pool.map(_play, jobs)]
    assert 0.40 <= float(np.mean(wins)) <= 0.48


def test_storyline_effects_are_at_least_3x_subtle() -> None:
    league, profiles, _ = _base()
    club = next(iter(profiles.clubs.values()))
    hot = _personality(aggression=1.0)(next(p for p in profiles.players.values()
                                            if p.club_id == club.club_id))  # fmt: skip
    subtle = Modifiers.for_player(hot, club, MatchContext()).effects["foul_rate"]
    story = Modifiers.for_player(hot, club, MatchContext(storyline=True)).effects["foul_rate"]
    assert subtle == pytest.approx(SUBTLE_CAP) and story == pytest.approx(STORYLINE_CAP)
    assert story >= 3 * subtle
