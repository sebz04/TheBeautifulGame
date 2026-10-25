"""Level 4: cards, substitutions, scenario beats, set pieces, and late-game fatigue."""

from collections import Counter
from functools import cache

import numpy as np
import pytest

from matchmind.engine import constants as C
from matchmind.engine import coupled
from matchmind.engine.coupled import Coupled
from matchmind.engine.lineup import match_meta
from matchmind.engine.modifiers import SUBTLE_CAP
from matchmind.engine.pitch import PITCH_LENGTH, attacks_right
from matchmind.engine.scenario import Beat, Scenario
from matchmind.engine.set_pieces import PENALTY_SPOT
from matchmind.engine.simulate import simulate_match
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles
from matchmind.schemas import MatchData, MatchMeta
from matchmind.stats.pitch_control import pitch_control_grid
from matchmind.stats.xt import load_xt, xt_added


@cache
def _league():  # type: ignore[no-untyped-def]
    return build_league()


@cache
def _profiles():  # type: ignore[no-untyped-def]
    return build_profiles(_league(), seed=2026)


@cache
def _meta(seed: int, fixture: int = 0) -> MatchMeta:
    return match_meta(_league(), build_fixtures(_league(), seed=2026)[fixture], seed=seed)


@cache
def _events(seed: int) -> MatchData:
    return simulate_match(_meta(seed, seed % 10), level=3, tracking=False, profiles=_profiles())


@cache
def _tracked(seed: int) -> MatchData:
    return simulate_match(_meta(seed), level=3, profiles=_profiles())


def _red_card_scenario(meta: MatchMeta) -> Scenario:
    return Scenario(scenario_id="red", title="Red", home_club_id=meta.home.club_id,
                    away_club_id=meta.away.club_id, seed=meta.seed,
                    beats=[Beat(minute=30, kind="red_card", team="home")])  # fmt: skip


@cache
def _red_card_match() -> tuple[MatchData, list[tuple[str, str, int]]]:
    calls: list[tuple[str, str, int]] = []
    real = coupled.formation_shape

    def spy(formation: str, phase: str, n: int = 11):  # type: ignore[no-untyped-def]
        calls.append((formation, phase, n))
        return real(formation, phase, n)  # type: ignore[arg-type]

    coupled.formation_shape = spy  # type: ignore[assignment]
    try:
        meta = _meta(7)
        data = simulate_match(meta, _red_card_scenario(meta), level=3, profiles=_profiles())
    finally:
        coupled.formation_shape = real
    return data, calls


@pytest.mark.slow
def test_cards_happen() -> None:
    cards = [e for s in range(1, 7) for e in _events(s).events if e.type == "card"]
    assert {e.extras["card"] for e in cards} <= {"yellow", "red"}
    yellows = sum(e.extras["card"] == "yellow" for e in cards) / 12
    assert 1.0 <= yellows <= 4.0


def test_subs_bring_on_bench_players() -> None:
    data = _tracked(7)
    subs = [e for e in data.events if e.type == "sub"]
    per_team = Counter(e.team_id for e in subs)
    assert min(per_team.values()) >= 1 and max(per_team.values()) <= 5
    for e in subs:
        later = next(f for f in data.frames if f.period == e.period and f.t >= e.t + 1.0)
        on = {p.player_id for p in later.players}
        assert e.receiver_id in on and e.player_id not in on, e.event_id


def test_red_card_reshapes() -> None:
    data, calls = _red_card_match()
    home = data.meta.home.club_id
    reds = [e for e in data.events if e.type == "card" and e.extras["card"] == "red"]
    first = next(e for e in reds if e.team_id == home)
    assert first.period == 2 or first.t >= 1800.0
    after = [f for f in data.frames if (f.period, f.t) > (first.period, first.t + 1.0)]
    assert all(sum(p.team_id == home for p in f.players) == 10 for f in after[::500])
    assert any(f == data.meta.home.formation and n == 10 for f, _, n in calls)


def test_ten_men_stats_finite() -> None:
    data, _ = _red_card_match()
    home = data.meta.home.club_id
    red = next(e for e in data.events if e.type == "card" and e.extras["card"] == "red"
               and e.team_id == home)  # fmt: skip
    frame = next(f for f in data.frames if (f.period, f.t) > (red.period, red.t + 60.0))
    keepers = frozenset({data.meta.home_squad[0].player_id, data.meta.away_squad[0].player_id})
    grid = pitch_control_grid(frame, home, goalkeepers=keepers,
                              attacks_right=attacks_right(True, frame.period))  # fmt: skip
    assert np.isfinite(grid).all()
    grid_xt = load_xt()
    later = [e for e in data.events if (e.period, e.t) > (red.period, red.t)]
    for e in later[:300]:
        v = xt_added(grid_xt, e, attacks_right(e.team_id == home, e.period))
        assert v is None or np.isfinite(v)


def _box_foul(inside: bool) -> Coupled:
    eng = Coupled(_meta(7), tracking=False, profiles=_profiles())
    eng.setup_period(1, 0.0)
    eng.pos[:] = eng.kickoff_shape()
    victim, fouler = 10, 12  # home forward, away defender; home attacks right
    at = np.array([PITCH_LENGTH - (10.0 if inside else 22.0), 34.0])
    eng.pos[victim], eng.pos[fouler] = at, at + (0.8, 0.0)
    eng.give_ball(victim, hold_s=5.0)
    eng.award_foul(fouler, victim, at)
    return eng


def test_fouls_in_box_are_penalties() -> None:
    eng = _box_foul(inside=True)
    assert eng.s.dead is not None and eng.s.dead.restart == "penalty"
    assert tuple(eng.s.dead.spot) == pytest.approx(PENALTY_SPOT)
    for _ in range(900):
        eng.tick()
        if any(e["type"] == "shot" for e in eng.events):
            break
    shot = next(e for e in eng.events if e["type"] == "shot")
    assert shot["extras"]["set_piece"] == "penalty"
    outside = _box_foul(inside=False)
    assert outside.s.dead is not None and outside.s.dead.restart == "free_kick"


@pytest.mark.slow
def test_set_pieces_are_taken() -> None:
    shots = [e for s in range(1, 9) for e in _events(s).events if e.type == "shot"]
    kinds = Counter(e.extras.get("set_piece") for e in shots)
    assert kinds["corner"] > 0 and kinds["free_kick"] > 0
    assert all(e.extras.get("header") for e in shots if e.extras.get("set_piece") == "corner")


def test_tactic_change_beat_changes_tactics() -> None:
    meta = _meta(7)
    scenario = Scenario(scenario_id="t", title="t", home_club_id=meta.home.club_id,
                        away_club_id=meta.away.club_id, seed=7,
                        beats=[Beat(minute=1, kind="tactic_change", team="away",
                                    params={"press_intensity": 0.95, "line_height": 0.9}),
                               Beat(minute=1, kind="goal", team="home")])  # fmt: skip
    eng = Coupled(meta, tracking=False, profiles=_profiles(), scenario=scenario)
    eng.setup_period(1, 0.0)
    for _ in range(round(90 / 0.1)):
        eng.tick()
    assert eng.tmods[1].press_intensity == 0.95 and eng.tmods[1].line_height == 0.9
    # The storyline window lifts the cap for the targeted teams' players only.
    assert max(abs(v) for m in eng.pmods[11:] for v in m.effects.values()) > SUBTLE_CAP
    assert max(abs(v) for m in eng.pmods[:11] for v in m.effects.values()) > SUBTLE_CAP


def test_fatigue_late() -> None:
    data = _tracked(7)
    keepers = {data.meta.home_squad[0].player_id, data.meta.away_squad[0].player_id}

    def mean_top(period: int, lo: float, hi: float) -> float:
        top: dict[str, float] = {}
        for f in data.frames:
            if f.period == period and lo <= f.t < hi:
                for p in f.players:
                    if p.player_id not in keepers:
                        top[p.player_id] = max(top.get(p.player_id, 0.0), np.hypot(p.vx, p.vy))
        return float(np.mean(list(top.values())))

    assert mean_top(2, 35 * 60, 45 * 60) < mean_top(1, 0, 10 * 60)


def test_scoring_shots_are_marked_as_goals() -> None:
    # Regression (TASK-10.3): xT reads goals from `shot.outcome`; level 3 marked every shot
    # False, including those that went in (directly or off a block or a parry).
    for seed in (1, 3):  # seed 3 has a pass that went straight in
        events = _events(seed).events
        goals = [e for e in events if e.type == "goal" and not e.extras.get("own_goal")]
        scored = [e for e in events if e.type == "shot" and e.outcome]
        assert len(scored) == len(goals), seed
        for g in goals:
            shot = next(e for e in reversed(events[: events.index(g)]) if e.type == "shot")
            assert shot.outcome and shot.player_id == g.player_id, g.event_id


def test_motion_matches_frames() -> None:
    """The engine's own motion tally (used without frames) agrees with the frames."""
    from matchmind.engine.coupled import simulate_with_motion
    from matchmind.engine.validate import _sprints

    data, motion = simulate_with_motion(_meta(7), profiles=_profiles())
    assert data.events == _tracked(7).events
    speeds: dict[str, list[list[float]]] = {}
    xy: dict[str, list[list[tuple[float, float]]]] = {}
    for f in data.frames:
        for p in f.players:
            runs = speeds.setdefault(p.player_id, [[], []])
            runs[f.period - 1].append(float(np.hypot(p.vx, p.vy)))
            xy.setdefault(p.player_id, [[], []])[f.period - 1].append((p.x, p.y))
    for pid, m in motion.items():
        if pid not in speeds:
            continue
        frame_dist = sum(float(np.hypot(*np.diff(np.array(seg), axis=0).T).sum())
                         for seg in xy[pid] if len(seg) > 1)  # fmt: skip
        assert m.distance_m == pytest.approx(frame_dist, rel=0.01, abs=5.0), pid
        top = max(max(seg, default=0.0) for seg in speeds[pid])
        assert m.top_speed_ms == pytest.approx(top, abs=0.02), pid
        sprints = sum(_sprints(np.array(seg)) for seg in speeds[pid])
        assert abs(m.sprints - sprints) <= 1, pid
        frames_on = sum(len(seg) for seg in speeds[pid])
        assert m.minutes == pytest.approx(frames_on * 0.1 / 60, abs=0.05), pid


def test_chemistry_raises_pair_completion() -> None:
    eng = Coupled(_meta(7), tracking=False, profiles=_profiles())
    pairs = [(i, j) for i in range(1, 11) for j in range(i + 1, 11)]
    chem = {p: eng.pair_chemistry(*p) for p in pairs}
    best, worst = max(pairs, key=chem.__getitem__), min(pairs, key=chem.__getitem__)
    assert chem[best] > chem[worst]
    assert eng.pair_completion(*best) > eng.pair_completion(*worst)
    assert 1 - SUBTLE_CAP - 1e-9 <= eng.pair_completion(*worst) <= 1 + SUBTLE_CAP + 1e-9
    neutral = Coupled(_meta(7), tracking=False)
    assert neutral.pair_completion(*best) == 1.0


def test_tired_and_low_work_rate_players_jog_less() -> None:
    eng = Coupled(_meta(7), tracking=False, profiles=_profiles())
    eng.setup_period(1, 0.0)
    eng.pos[:] = eng.kickoff_shape() + 20.0  # everyone far from his spot
    _, fresh = eng.shape()
    eng.energy[:] = 0.3
    _, tired = eng.shape()
    assert np.all(tired[1:11] < fresh[1:11])
    factor = eng.urgency_factor()
    work = np.array([m.offball_distance for m in eng.pmods])
    assert factor == pytest.approx(work * (C.TIRED_URGENCY + (1 - C.TIRED_URGENCY) * 0.3))
