from collections import Counter
from functools import cache
from pathlib import Path

import pytest

from matchmind.engine.lineup import match_meta
from matchmind.engine.match_io import read_match, write_match
from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH, distance
from matchmind.engine.simulate import simulate_match
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.schemas import MatchData, MatchMeta, TrackingFrame


@cache
def _meta(seed: int) -> MatchMeta:
    league = build_league()
    return match_meta(league, build_fixtures(league, seed=2026)[0], seed=seed)


@cache
def _match(seed: int) -> MatchData:
    return simulate_match(_meta(seed), level=1)


@cache
def _period_frames(seed: int, period: int) -> list[TrackingFrame]:
    return [f for f in _match(seed).frames if f.period == period]


def _frame_at(data: MatchData, period: int, t: float) -> TrackingFrame:
    frames = _period_frames(data.meta.seed, period)
    idx = min(max(round(t * 10), 0), len(frames) - 1)
    assert abs(frames[idx].t - idx / 10) < 1e-6
    return frames[idx]


def test_deterministic() -> None:
    a = simulate_match(_meta(7), level=1)
    assert a.events == _match(7).events
    assert a.frames[-1] == _match(7).frames[-1]
    assert simulate_match(_meta(8), level=1).events != a.events


def test_frame_rate() -> None:
    data = _match(7)
    meta = data.meta
    assert len(data.frames) == sum(round((2700 + a) * 10) for a in meta.added_time_s)
    assert [f.frame for f in data.frames] == list(range(len(data.frames)))
    for period in (1, 2):
        ts = [f.t for f in data.frames if f.period == period]
        assert ts[0] == 0.0
        assert all(abs((b - a) - 0.1) < 1e-6 for a, b in zip(ts, ts[1:], strict=False))


def test_pass_endpoints_consistent() -> None:
    data = _match(7)
    passes = [e for e in data.events if e.type == "pass" and e.outcome]
    assert len(passes) > 200
    for e in passes:
        assert e.end_x is not None and e.end_y is not None and e.ball_speed_ms
        start = _frame_at(data, e.period, e.t)
        passer = next(p for p in start.players if p.player_id == e.player_id)
        assert distance((passer.x, passer.y), (e.x, e.y)) <= 1.5, e.event_id
        flight = distance((e.x, e.y), (e.end_x, e.end_y)) / e.ball_speed_ms
        end = _frame_at(data, e.period, e.t + flight)
        receiver = next(p for p in end.players if p.player_id == e.receiver_id)
        assert distance((receiver.x, receiver.y), (e.end_x, e.end_y)) <= 2.0, e.event_id


def test_eleven_per_side_without_cards() -> None:
    data = _match(7)
    assert not any(e.type == "card" for e in data.events)
    home, away = data.meta.home.club_id, data.meta.away.club_id
    for f in data.frames[::50]:
        teams = Counter(p.team_id for p in f.players)
        assert teams == {home: 11, away: 11}


def test_everyone_stays_on_the_pitch() -> None:
    for f in _match(7).frames[::25]:
        assert 0 <= f.ball[0] <= PITCH_LENGTH and 0 <= f.ball[1] <= PITCH_WIDTH
        for p in f.players:
            assert -2 <= p.x <= PITCH_LENGTH + 2 and -2 <= p.y <= PITCH_WIDTH + 2
            assert (p.vx**2 + p.vy**2) ** 0.5 <= 10.5  # faster than any human sprint


def test_teams_switch_ends_at_half_time() -> None:
    data = _match(7)
    home_gk = data.meta.home_squad[0].player_id

    def mean_x(period: int) -> float:
        xs = [
            p.x for f in data.frames[::20] if f.period == period
            for p in f.players if p.player_id == home_gk
        ]  # fmt: skip
        return sum(xs) / len(xs)

    assert mean_x(1) < 25 and mean_x(2) > PITCH_LENGTH - 25


def test_plausible_match_volume() -> None:
    data = _match(7)
    by_type = Counter(e.type for e in data.events)
    passes = [e for e in data.events if e.type == "pass"]
    completion = sum(bool(e.outcome) for e in passes) / len(passes)
    assert 600 <= len(passes) <= 1300
    assert 0.65 <= completion <= 0.92
    assert 12 <= by_type["shot"] <= 40
    assert by_type["goal"] <= 9
    # A goal in the last seconds of a half can leave no time to kick off again.
    assert 2 <= by_type["kickoff"] <= 2 + by_type["goal"]
    teams = Counter(e.team_id for e in passes)
    assert len(teams) == 2 and min(teams.values()) > 0.3 * len(passes)


def test_event_ids_sequential_and_time_ordered() -> None:
    data = _match(7)
    ids = [e.event_id for e in data.events]
    assert ids == [f"{data.meta.match_id}-e{i:05d}" for i in range(len(ids))]
    keys = [(e.period, e.t) for e in data.events]
    assert keys == sorted(keys)


def test_level_three_not_ready() -> None:
    with pytest.raises(NotImplementedError):
        simulate_match(_meta(7), level=3)


def test_simulated_match_round_trips(tmp_path: Path) -> None:
    write_match(_match(7), tmp_path)
    back = read_match(tmp_path)
    assert back.events == _match(7).events
    assert back.frames[::997] == _match(7).frames[::997]
    assert len(back.frames) == len(_match(7).frames)
