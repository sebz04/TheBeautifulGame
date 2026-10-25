from functools import cache

import numpy as np
import pytest

from matchmind.engine.formations import formation_anchors
from matchmind.engine.lineup import FORMATION_LINES
from matchmind.engine.scenario import SCENARIO_DIR, load_scenario, scenario_meta
from matchmind.engine.simulate import simulate_match
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles
from matchmind.schemas import Event, EventType, MatchData, Moment, PlayerPos, TrackingFrame
from matchmind.stats.moments import classify_formation, detect_moments, merge_moments
from matchmind.stats.xt import load_xt

GRID = load_xt()


def _empty_match() -> MatchData:
    league = build_league()
    s = load_scenario(SCENARIO_DIR / "chess_match_0_0.toml")
    meta = scenario_meta(league, s)
    return MatchData(meta=meta, events=[], frames=[])


def _with(
    events: list[tuple[EventType, str, float, dict[str, object]]], period: int = 1
) -> MatchData:
    """A match shell with hand-made events: (type, 'home'|'away', t, extras)."""
    data = _empty_match()
    ids = {"home": data.meta.home.club_id, "away": data.meta.away.club_id}
    players = {"home": data.meta.home_squad[9].player_id, "away": data.meta.away_squad[9].player_id}
    evs = [Event(event_id=f"{data.meta.match_id}-e{n:05d}", match_id=data.meta.match_id,
                 period=period, t=t, type=type_, team_id=ids[side],  # type: ignore[arg-type]
                 player_id=players[side], x=80.0, y=34.0, end_x=None, end_y=None, outcome=None,
                 receiver_id=None, ball_speed_ms=None, extras=extras)
           for n, (type_, side, t, extras) in enumerate(events)]  # fmt: skip
    return data.model_copy(update={"events": evs})


def _kinds(moments: list[Moment]) -> list[str]:
    return [m.kind for m in moments]


def test_goals_red_cards_and_big_chances() -> None:
    data = _with([("shot", "home", 100.0, {"xg": 0.31}), ("goal", "home", 101.0, {}),
                  ("shot", "away", 400.0, {"xg": 0.2}),
                  ("card", "away", 900.0, {"card": "red"}),
                  ("card", "home", 950.0, {"card": "yellow"})])  # fmt: skip
    moments = detect_moments(data, GRID)
    kinds = _kinds(moments)
    assert kinds.count("big_chance") == 1 and kinds.count("goal") == 1
    assert kinds.count("red_card") == 1
    red = next(m for m in moments if m.kind == "red_card")
    assert red.team_id == data.meta.away.club_id and red.level == "player" and red.player_id
    assert [m.moment_id for m in moments] == [f"{data.meta.match_id}-m{n:03d}"
                                              for n in range(len(moments))]  # fmt: skip
    assert [(m.period, m.t_start) for m in moments] == sorted((m.period, m.t_start)
                                                             for m in moments)  # fmt: skip


def test_offside_trap() -> None:
    caught = [("offside", "away", t, {}) for t in (100.0, 500.0, 1100.0)]
    moments = detect_moments(_with(caught), GRID)
    trap = [m for m in moments if m.kind == "offside_trap"]
    assert len(trap) == 1
    data = _with(caught)
    assert trap[0].team_id == data.meta.home.club_id and trap[0].trigger_value == 3
    spread = [("offside", "away", t, {}) for t in (100.0, 900.0, 1400.0)]  # 1300 s > 20 min
    assert "offside_trap" not in _kinds(detect_moments(_with(spread), GRID))


def test_corner_pressure() -> None:
    # Corners for home: the away team put the ball behind.
    corners = [("out", "away", t, {"restart": "corner"}) for t in (100.0, 200.0, 350.0)]
    moments = [m for m in detect_moments(_with(corners), GRID) if m.kind == "corner_pressure"]
    assert len(moments) == 1 and moments[0].team_id == _with(corners).meta.home.club_id
    slow = [("out", "away", t, {"restart": "corner"}) for t in (100.0, 300.0, 500.0)]
    assert "corner_pressure" not in _kinds(detect_moments(_with(slow), GRID))


def test_close_moments_merge() -> None:
    data = _with([("shot", "home", 100.0, {"xg": 0.3}), ("shot", "home", 140.0, {"xg": 0.4}),
                  ("shot", "home", 300.0, {"xg": 0.3})])  # fmt: skip
    chances = [m for m in detect_moments(data, GRID) if m.kind == "big_chance"]
    assert len(chances) == 2
    assert len(chances[0].event_ids) == 2 and chances[0].t_end == 140.0
    assert chances[0].trigger_value == 0.4  # the larger trigger survives


def test_merge_keeps_kinds_and_teams_apart() -> None:
    m = Moment(moment_id="x", match_id="m", period=1, t_start=10.0, t_end=10.0, kind="goal",
               level="player", team_id="a", player_id="p", trigger_metric="goal",
               trigger_value=1.0, event_ids=["e1"])  # fmt: skip
    other_team = m.model_copy(update={"team_id": "b", "t_start": 20.0, "t_end": 20.0})
    other_kind = m.model_copy(update={"kind": "big_chance", "t_start": 30.0, "t_end": 30.0})
    assert len(merge_moments([m, other_team, other_kind])) == 3


def test_classify_formation_templates() -> None:
    for formation in FORMATION_LINES:
        assert classify_formation(formation_anchors(formation)[1:]) == formation


def _frames_for_shift(meta_home: str) -> list[TrackingFrame]:
    """Home holds a 4-4-2 for 10 minutes, then a 3-5-2 for 10 minutes."""
    frames = []
    for k in range(0, 12000, 10):  # one frame per second
        formation = "4-4-2" if k < 6000 else "3-5-2"
        a = formation_anchors(formation)
        players = [PlayerPos(player_id=f"p{i}", team_id=meta_home, x=float(x), y=float(y),
                             vx=0.0, vy=0.0) for i, (x, y) in enumerate(a)]  # fmt: skip
        frames.append(TrackingFrame(match_id="m", frame=k, period=1, t=k / 10,
                                    ball=(50.0, 34.0, 0.1), players=players))  # fmt: skip
    return frames


def test_formation_shift_detected() -> None:
    data = _empty_match()
    data = data.model_copy(update={"frames": _frames_for_shift(data.meta.home.club_id)})
    shifts = [m for m in detect_moments(data, GRID) if m.kind == "formation_shift"]
    assert len(shifts) == 1
    assert shifts[0].team_id == data.meta.home.club_id
    assert 600.0 <= shifts[0].t_start <= 600.0 + 240.0


@cache
def _storyline(scenario_id: str, seed: int | None = None) -> MatchData:
    league = build_league()
    s = load_scenario(SCENARIO_DIR / f"{scenario_id}.toml")
    if seed is not None:
        s = s.model_copy(update={"seed": seed})
    return simulate_match(scenario_meta(league, s), s, level=3, tracking=False,
                          profiles=build_profiles(league, seed=2026))  # fmt: skip


def test_red_card_moment_in_its_storyline() -> None:
    reds = [m for m in detect_moments(_storyline("comeback_red_card"), GRID)
            if m.kind == "red_card"]  # fmt: skip
    assert reds


@pytest.mark.slow
def test_scripted_pressing_collapse() -> None:
    """A pressing collapse within 5 min of `press_collapse`'s fatigue beat on at least one
    of six seeds. Not every seed: when a 0.95 press fades on its own before the beat,
    there is legitimately nothing left to collapse (and matches differ across platforms).
    """
    beat = next(b for b in load_scenario(SCENARIO_DIR / "press_collapse.toml").beats
                if b.kind == "fatigue_spike")  # fmt: skip
    hits = []
    for seed in (None, 1, 2, 3, 4, 5):
        data = _storyline("press_collapse", seed)
        collapses = [m for m in detect_moments(data, GRID) if m.kind == "pressing_collapse"
                     and m.team_id == data.meta.away.club_id]  # fmt: skip
        minutes = [(45.0 if m.period == 2 else 0.0) + m.t_start / 60 for m in collapses]
        hits.append(any(abs(mm - beat.minute) <= 5.0 for mm in minutes))
    assert any(hits), hits


def test_moment_triggers_are_finite() -> None:
    moments = detect_moments(_storyline("derby_chaos"), GRID)
    assert moments and all(np.isfinite(m.trigger_value) for m in moments)
    assert {m.level for m in moments} <= {"game", "team", "player"}
