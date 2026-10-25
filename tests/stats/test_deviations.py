import math
from collections import Counter
from functools import cache

import numpy as np
import pytest

from matchmind.engine.lineup import match_meta
from matchmind.engine.simulate import simulate_match
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles
from matchmind.league.season import Season, simulate_history
from matchmind.schemas import Event, MatchData
from matchmind.stats.baselines import PlayerBaseline, expected_at, player_baselines
from matchmind.stats.deviations import (
    TRACKED_STATS,
    ExpectContext,
    assess,
    detect_deviations,
    deviation_moments,
    tail_p,
)
from matchmind.stats.player_lines import PlayerMatchLine


@cache
def _setup():  # type: ignore[no-untyped-def]
    league = build_league()
    return league, build_profiles(league, seed=2026), build_fixtures(league, seed=2026)


def _line(pid: str, club: str, n: int, minutes: int, **counts: int) -> PlayerMatchLine:
    return PlayerMatchLine(match_id=f"r{n:02d}-x-v-y", round=n, player_id=pid, club_id=club,
                           minutes=minutes, **counts)  # fmt: skip


def _season(lines: list[PlayerMatchLine]) -> Season:
    return Season(rounds=9, results=[], standings=[], player_lines=lines, milestones={},
                  discipline={}, unavailable={})  # fmt: skip


def _same_role(n: int) -> list[str]:
    _, profiles, _ = _setup()
    by_role: dict[str, list[str]] = {}
    for pid, p in sorted(profiles.players.items()):
        by_role.setdefault(p.style.role, []).append(pid)
    return next(ids for role, ids in sorted(by_role.items()) if len(ids) >= n)[:n]


def test_shrinkage() -> None:
    _, profiles, _ = _setup()
    rookie, veteran, *others = _same_role(6)
    club = profiles.players[rookie].club_id
    lines = [_line(rookie, club, 1, 90, forward_passes=40)]
    lines += [_line(veteran, club, k, 90, forward_passes=40) for k in range(1, 10)]
    lines += [_line(pid, club, k, 90, forward_passes=18) for pid in others for k in range(1, 10)]
    base = player_baselines(_season(lines), profiles)
    role_mean = (40 * 10 + 18 * 36) / 46  # all role minutes are 90 per line
    r, v = base[rookie].per90["forward_passes"], base[veteran].per90["forward_passes"]
    assert abs(r - role_mean) < abs(r - 40)  # 90 minutes: near the role mean
    assert abs(v - 40) < abs(v - role_mean)  # 810 minutes: near his own rate
    assert base[rookie].minutes == 90 and base[veteran].minutes == 810
    # A player who never played gets his role's rate.
    role = profiles.players[rookie].style.role
    used = {rookie, veteran, *others}
    unused = next(pid for pid, p in profiles.players.items()
                  if p.style.role == role and pid not in used)  # fmt: skip
    assert base[unused].per90["forward_passes"] == pytest.approx(role_mean)


def test_tail_p_values() -> None:
    # Poisson(12): P(X <= 3) = 0.00229.
    assert tail_p(3, 12.0, 1.0, "under") == pytest.approx(0.00229, abs=1e-4)
    assert tail_p(12, 12.0, 1.0, "under") > 0.5
    assert tail_p(20, 12.0, 1.0, "over") == pytest.approx(0.0214, abs=1e-3)
    # Overdispersion widens the tails.
    assert tail_p(3, 12.0, 2.0, "under") > tail_p(3, 12.0, 1.0, "under")


def test_example_forward_passes() -> None:
    base = PlayerBaseline(player_id="p", minutes=900, per90={"forward_passes": 18.0},
                          dispersion={"forward_passes": 1.0})  # fmt: skip
    expected = expected_at(base, "forward_passes", 60.0, ExpectContext())
    assert expected == pytest.approx(12.0)
    dev = assess(base, "forward_passes", observed=3, minutes_played=60.0, ctx=ExpectContext())
    assert dev is not None and dev.direction == "under" and dev.p_value < 0.01
    assert dev.expected == pytest.approx(12.0) and dev.baseline_per90 == 18.0


def test_no_flag_early_or_small() -> None:
    rates = {"forward_passes": 18.0, "goals": 0.6}
    base = PlayerBaseline(player_id="p", minutes=900, per90=rates,
                          dispersion={"forward_passes": 1.0, "goals": 1.0})  # fmt: skip
    assert assess(base, "forward_passes", 0, minutes_played=20.0, ctx=ExpectContext()) is None
    assert assess(base, "goals", 0, minutes_played=80.0, ctx=ExpectContext()) is None  # exp < 5
    assert assess(base, "goals", 2, minutes_played=80.0, ctx=ExpectContext()) is None  # obs < 3


def test_possession_and_red_card_adjustments() -> None:
    base = PlayerBaseline(player_id="p", minutes=900, per90={"passes": 45.0, "tackles": 3.0},
                          dispersion={"passes": 1.0, "tackles": 1.0})  # fmt: skip
    neutral = expected_at(base, "passes", 90.0, ExpectContext())
    dominant = expected_at(base, "passes", 90.0, ExpectContext(possession_share=0.6))
    assert dominant > neutral
    assert expected_at(base, "tackles", 90.0, ExpectContext(possession_share=0.6)) < 3.0
    assert expected_at(base, "passes", 90.0, ExpectContext(team_men=10)) < neutral
    assert set(TRACKED_STATS) >= {"passes", "forward_passes", "tackles", "shots", "sprints"}


def _starved_match() -> tuple[MatchData, dict[str, PlayerBaseline]]:
    """A real match where one home midfielder's passes are removed after kickoff."""
    league, profiles, fixtures = _setup()
    meta = match_meta(league, fixtures[0], seed=7)
    data = simulate_match(meta, level=3, tracking=False, profiles=profiles)
    target = meta.home_squad[6].player_id
    events: list[Event] = [
        e for e in data.events if not (e.type == "pass" and e.player_id == target)
    ]
    data = data.model_copy(update={"events": events})
    base = {p.player_id: PlayerBaseline(player_id=p.player_id, minutes=900,
                                         per90={s: 1.0 for s in TRACKED_STATS} | {"passes": 50.0},
                                         dispersion={s: 1.0 for s in TRACKED_STATS})
            for p in meta.home_squad + meta.away_squad}  # fmt: skip
    return data, base


def test_detect_deviations_and_moments() -> None:
    data, base = _starved_match()
    target = data.meta.home_squad[6].player_id
    early = detect_deviations(data, base, (1, 20 * 60.0), stats=("passes",))
    assert early == []
    later = detect_deviations(data, base, (1, 40 * 60.0), stats=("passes",))
    assert any(d.player_id == target and d.direction == "under" for d in later)
    pairs = deviation_moments(data, base, stats=("passes",))
    assert pairs and all(m.kind == "player_deviation" and m.level == "player" for m, _ in pairs)
    flagged = Counter((d.player_id, d.stat) for _, d in pairs)
    assert max(flagged.values()) == 1  # each player-stat is flagged once
    first = next(m for m, d in pairs if d.player_id == target)
    assert first.trigger_metric == "passes" and first.trigger_value == 0.0
    per_window = Counter((m.period, m.t_start) for m, _ in pairs)
    assert max(per_window.values()) <= 3
    assert all(math.isfinite(d.p_value) and d.p_value < 0.01 for _, d in pairs)


# ---- season-based (slow) ----------------------------------------------------------------


@cache
def _history() -> Season:
    league, profiles, fixtures = _setup()
    return simulate_history(league, profiles, fixtures, rounds=9)


@pytest.mark.slow
def test_false_alarm_rate() -> None:
    league, profiles, fixtures = _setup()
    base = player_baselines(_history(), profiles)
    flags = []
    for seed in range(1, 21):
        fixture = fixtures[200 + seed]  # later rounds, not in the history
        data = simulate_match(match_meta(league, fixture, seed=seed), level=3, tracking=False,
                              profiles=profiles)  # fmt: skip
        flags.append(len(deviation_moments(data, base)))
    assert np.mean(flags) / 2 <= 1.0


def test_club_possession_in_baselines() -> None:
    _, profiles, _ = _setup()
    a, b = "chapinero", "laureles"
    pa = next(pid for pid, p in profiles.players.items() if p.club_id == a)
    pb = next(pid for pid, p in profiles.players.items() if p.club_id == b)
    lines = [_line(pa, a, 1, 90, passes=60), _line(pb, b, 1, 90, passes=40)]
    lines = [line.model_copy(update={"match_id": "r01-chapinero-v-laureles"}) for line in lines]
    base = player_baselines(_season(lines), profiles)
    assert base[pa].club_possession == pytest.approx(0.6)
    assert base[pb].club_possession == pytest.approx(0.4)
    other = next(pid for pid, p in profiles.players.items() if p.club_id not in (a, b))
    assert base[other].club_possession == 0.5  # no matches: neutral


def test_correlated_stats_flag_once_per_player() -> None:
    data, base = _starved_match()
    target = data.meta.home_squad[6].player_id
    rates = {"passes": 50.0, "completed": 40.0, "forward_passes": 20.0}
    base = {pid: b.model_copy(update={"per90": b.per90 | rates}) for pid, b in base.items()}
    pairs = deviation_moments(data, base, stats=("passes", "completed", "forward_passes"))
    assert len([d for _, d in pairs if d.player_id == target]) == 1
