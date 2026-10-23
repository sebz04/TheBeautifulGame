from collections import Counter
from functools import cache

import pytest

from matchmind.engine.coupled import Motion, simulate_with_motion
from matchmind.engine.lineup import match_meta
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles
from matchmind.schemas import Event, EventType, MatchData
from matchmind.stats.player_lines import PlayerMatchLine, player_match_lines


@cache
def _match() -> tuple[MatchData, dict[str, Motion]]:
    league = build_league()
    meta = match_meta(league, build_fixtures(league, seed=2026)[3], seed=5)
    return simulate_with_motion(meta, tracking=False, profiles=build_profiles(league, seed=2026))


def test_player_lines_match_events() -> None:
    data, motion = _match()
    lines = {line.player_id: line for line in player_match_lines(data, motion, round_=4)}
    assert set(lines) == set(motion)
    ev = data.events
    by = Counter((e.type, e.player_id) for e in ev)
    for pid, line in lines.items():
        assert line.round == 4 and line.match_id == data.meta.match_id
        assert line.passes == by[("pass", pid)]
        assert line.completed == sum(e.type == "pass" and e.outcome and e.player_id == pid
                                     for e in ev)  # fmt: skip
        assert line.shots == by[("shot", pid)]
        assert line.tackles == by[("tackle", pid)]
        assert line.interceptions == by[("interception", pid)]
        assert line.fouls == by[("foul", pid)]
        assert line.dribbles == by[("carry", pid)]
        assert line.goals == sum(e.type == "goal" and e.player_id == pid
                                 and not e.extras.get("own_goal") for e in ev)  # fmt: skip
        assert line.yellow == sum(e.type == "card" and e.player_id == pid
                                  and e.extras["card"] == "yellow" for e in ev)  # fmt: skip
        assert line.distance_km == pytest.approx(motion[pid].distance_m / 1000, abs=1e-3)
        assert line.minutes == round(motion[pid].minutes)
        assert line.completed <= line.passes and line.shots_on_target <= line.shots
        assert line.key_passes <= line.completed and line.progressive_passes <= line.completed
    home = data.meta.home.club_id
    team_goals = sum(e.type == "goal" and e.team_id == home and not e.extras.get("own_goal")
                     for e in ev)  # fmt: skip
    assert sum(line.goals for line in lines.values() if line.club_id == home) == team_goals
    assert sum(line.assists for line in lines.values()) <= sum(
        line.goals for line in lines.values()
    )


def _ev(n: int, type_: EventType, team: str, player: str, x: float, end: tuple[float, float] | None
        = None, outcome: bool | None = True, receiver: str | None = None,
        **extras: object) -> Event:  # fmt: skip
    return Event(event_id=f"m-e{n:05d}", match_id="m", period=1, t=float(n), type=type_,
                 team_id=team, player_id=player, x=x, y=34.0,
                 end_x=None if end is None else end[0], end_y=None if end is None else end[1],
                 outcome=outcome, receiver_id=receiver, ball_speed_ms=None,
                 extras=dict(extras))  # fmt: skip


def test_key_passes_assists_and_progressive_passes() -> None:
    data, motion = _match()
    home = data.meta.home.club_id
    a, b = data.meta.home_squad[5].player_id, data.meta.home_squad[10].player_id
    events = [
        _ev(0, "pass", home, a, 50.0, (75.0, 34.0), receiver=b),  # progressive (55 -> 30 m)
        _ev(1, "carry", home, b, 75.0, (90.0, 34.0)),
        _ev(2, "shot", home, b, 90.0, (105.0, 34.0), xg=0.2),
        _ev(3, "goal", home, b, 105.0),
        _ev(4, "pass", home, a, 60.0, (62.0, 40.0), receiver=b),  # short, sideways
    ]
    toy = data.model_copy(update={"events": events})
    lines = {line.player_id: line for line in player_match_lines(toy, motion, round_=1)}
    assert lines[a].key_passes == 1 and lines[a].assists == 1
    assert lines[a].progressive_passes == 1 and lines[a].forward_passes == 1
    assert lines[b].goals == 1 and lines[b].shots_on_target == 1 and lines[b].xg == 0.2
    assert lines[b].box_touches >= 1
    assert isinstance(lines[a], PlayerMatchLine)
