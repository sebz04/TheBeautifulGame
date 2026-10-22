"""Level-3 engine: the event-coupled 10 Hz loop."""

from collections import Counter
from functools import cache

import numpy as np
import pytest

from matchmind.engine.ball import restart_for
from matchmind.engine.coupled import Coupled
from matchmind.engine.decisions import Option
from matchmind.engine.lineup import match_meta
from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH, attacks_right, distance
from matchmind.engine.simulate import simulate_match
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.schemas import MatchData, MatchMeta, TrackingFrame


@cache
def _meta(seed: int, fixture: int = 0) -> MatchMeta:
    league = build_league()
    return match_meta(league, build_fixtures(league, seed=2026)[fixture], seed=seed)


@cache
def _match(seed: int) -> MatchData:
    return simulate_match(_meta(seed), level=3)


@cache
def _events_only(seed: int) -> MatchData:
    fixtures = len(build_fixtures(build_league(), seed=2026))
    return simulate_match(_meta(seed, ((seed - 1) * 19) % fixtures), level=3, tracking=False)


@cache
def _period_frames(seed: int, period: int) -> list[TrackingFrame]:
    return [f for f in _match(seed).frames if f.period == period]


def _frame_at(seed: int, period: int, t: float) -> TrackingFrame:
    frames = _period_frames(seed, period)
    return frames[min(max(round(t * 10), 0), len(frames) - 1)]


def _where(frame: TrackingFrame, player_id: str | None) -> tuple[float, float]:
    p = next(p for p in frame.players if p.player_id == player_id)
    return p.x, p.y


def test_level3_deterministic() -> None:
    again = simulate_match(_meta(7), level=3)
    assert again.events == _match(7).events
    assert again.frames[-1] == _match(7).frames[-1]
    assert _events_only(3).events != _events_only(4).events


def test_events_only_mode_gives_identical_events() -> None:
    assert simulate_match(_meta(7), level=3, tracking=False).events == _match(7).events


def test_frame_rate_and_eleven_per_side() -> None:
    data = _match(7)
    assert len(data.frames) == sum(round((2700 + a) * 10) for a in data.meta.added_time_s)
    assert [f.frame for f in data.frames] == list(range(len(data.frames)))
    home, away = data.meta.home.club_id, data.meta.away.club_id
    for f in data.frames[::97]:
        assert Counter(p.team_id for p in f.players) == {home: 11, away: 11}


def test_level3_consistency() -> None:
    """Events and frames agree: the passer kicks it, the receiver controls it."""
    data = _match(7)
    passes = [e for e in data.events if e.type == "pass" and e.outcome]
    assert len(passes) > 300
    for e in passes:
        start = _frame_at(7, e.period, e.t)
        assert distance(_where(start, e.player_id), (e.x, e.y)) <= 1.5, e.event_id
        assert distance(start.ball[:2], (e.x, e.y)) <= 1.5, e.event_id
        assert e.end_x is not None and e.end_y is not None
        end = _frame_at(7, e.period, e.extras["arrival_t"])
        assert distance(_where(end, e.receiver_id), (e.end_x, e.end_y)) <= 1.5, e.event_id
        assert distance(end.ball[:2], (e.end_x, e.end_y)) <= 1.5, e.event_id


def test_decisions_recorded_on_events() -> None:
    chosen = [e for e in _match(7).events if e.type in ("pass", "shot", "clearance")
              and "best_option" in e.extras]  # fmt: skip
    assert len(chosen) > 300
    assert all(e.extras["chosen_score"] <= e.extras["best_score"] + 1e-9 for e in chosen)


def test_physically_plausible_frames() -> None:
    for f in _match(7).frames[::25]:
        assert -0.5 <= f.ball[0] <= PITCH_LENGTH + 0.5 and -0.5 <= f.ball[1] <= PITCH_WIDTH + 0.5
        for p in f.players:
            assert -3 <= p.x <= PITCH_LENGTH + 3 and -3 <= p.y <= PITCH_WIDTH + 3
            assert (p.vx**2 + p.vy**2) ** 0.5 <= 10.0 + 1e-6


def test_event_ids_sequential_and_time_ordered() -> None:
    data = _match(7)
    assert [e.event_id for e in data.events] == [
        f"{data.meta.match_id}-e{i:05d}" for i in range(len(data.events))
    ]
    keys = [(e.period, e.t) for e in data.events]
    assert keys == sorted(keys)


def test_out_of_play_happens_on_the_lines_by_last_touch() -> None:
    data = _match(7)
    outs = [e for e in data.events if e.type == "out"]
    assert len(outs) > 20
    home = data.meta.home.club_id
    for e in outs:
        on_line = e.x in (0.0, PITCH_LENGTH) or e.y in (0.0, PITCH_WIDTH)
        assert on_line, e.event_id
        right = attacks_right(e.team_id == home, e.period)  # the team that touched it last
        assert e.extras["restart"] == restart_for((e.x, e.y), right), e.event_id


def test_corners_happen() -> None:
    corners = [sum(e.extras.get("restart") == "corner" for e in _events_only(s).events if
                   e.type == "out") for s in range(1, 21)]  # fmt: skip
    assert np.mean(corners) / 2 > 2.0


def test_clearances_blocks_and_parries_happen() -> None:
    events = [e for s in range(1, 6) for e in _events_only(s).events]
    assert any(e.type == "clearance" for e in events)
    assert any(e.type == "shot" and e.extras.get("blocked") for e in events)
    assert any(e.type == "save" and e.extras.get("parried") for e in events)


# ---- offside from a mistimed run ------------------------------------------------------


def _offside_scene(timing_error_s: float) -> tuple[Coupled, int, int]:
    """Home attacks right. The away back line holds at x = 80; home's striker hovers
    onside; the carrier, 18 m behind, plays the through ball at the next decision."""
    eng = Coupled(_meta(7), tracking=False)
    eng.setup_period(1, 0.0)
    eng.pos[:] = eng.kickoff_shape()
    eng.pos[11 + 1 : 11 + 5] = [(80.0, y) for y in (14.0, 28.0, 40.0, 54.0)]  # away back four
    eng.pos[11] = (100.0, 34.0)  # away keeper
    eng.pos[11 + 5 : 22] = [(70.0, 20.0 + 5 * k) for k in range(6)]
    carrier, runner = 6, 10
    eng.pos[carrier] = (62.0, 34.0)
    eng.pos[runner] = (79.8, 33.0)  # hovering 0.2 m onside
    eng.vel[:] = 0.0
    eng.give_ball(carrier, hold_s=1.0)
    eng.force_run(runner, timing_error_s)

    def through(options: list[Option]) -> Option:
        eng.chooser = None  # only the carrier's next decision is scripted
        return next(o for o in options if o.kind == "through"
                    and o.target_player_id == eng.ids[runner])  # fmt: skip

    eng.chooser = through
    return eng, carrier, runner


def test_offside_called_on_mistimed_run() -> None:
    eng, _, runner = _offside_scene(timing_error_s=0.5)
    for _ in range(60):
        eng.tick()
    offsides = [e for e in eng.events if e["type"] == "offside"]
    assert len(offsides) == 1
    assert offsides[0]["player_id"] == eng.ids[runner]
    assert offsides[0]["extras"]["timing_error_s"] == pytest.approx(0.5)
    assert eng.s.dead is not None and eng.s.dead.restart == "free_kick"
    assert eng.team_of[eng.s.dead.taker] == 1  # the defenders restart


def test_well_timed_run_is_onside() -> None:
    eng, _, _ = _offside_scene(timing_error_s=0.0)
    for _ in range(60):
        eng.tick()
    assert not [e for e in eng.events if e["type"] == "offside"]
    assert [e for e in eng.events if e["type"] == "pass"]


def test_profiles_turn_on_modifiers() -> None:
    from matchmind.engine.coupled import mods_from_profiles
    from matchmind.engine.modifiers import SUBTLE_CAP
    from matchmind.league.profiles import build_profiles

    profiles = build_profiles(build_league(), seed=2026)
    player_mods, team_mods = mods_from_profiles(_meta(7), profiles)
    assert len(player_mods) == 22
    assert all(abs(v) <= SUBTLE_CAP + 1e-9 for m in player_mods for v in m.effects.values())
    clubs = (profiles.clubs[_meta(7).home.club_id], profiles.clubs[_meta(7).away.club_id])
    assert team_mods[0].press_intensity == clubs[0].tactical_identity.press_intensity
    with_mods = simulate_match(_meta(7), level=3, tracking=False, profiles=profiles)
    assert with_mods.events != _match(7).events


def test_level3_matches_carry_their_engine_version() -> None:
    assert _match(7).meta.engine_version == "l3-0.1"
    assert _match(7).meta.model_copy(update={"engine_version": "x"}) != _meta(7)
