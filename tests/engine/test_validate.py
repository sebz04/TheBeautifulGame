import json

import pytest

from matchmind.engine.realism_ranges import RANGES
from matchmind.engine.validate import RealismReport, validate_many, validate_match
from matchmind.schemas import (
    Club,
    Event,
    EventType,
    MatchData,
    MatchMeta,
    Player,
    PlayerPos,
    TrackingFrame,
)

MID = "r01-h-v-a"


def _club(cid: str) -> Club:
    return Club(club_id=cid, name=cid, short=cid.upper()[:3].ljust(3, "X"),
                primary_color="#000000", secondary_color="#FFFFFF", formation="4-3-3")  # fmt: skip


def _player(pid: str, cid: str, pos: str = "MF") -> Player:
    return Player(player_id=pid, name=pid, club_id=cid, number=5, position=pos,  # type: ignore[arg-type]
                  pace=0.5, skill=0.5, stamina=0.5)  # fmt: skip


class _Events:
    def __init__(self) -> None:
        self.items: list[Event] = []

    def add(self, type_: EventType, team: str, x: float = 50.0, outcome: bool | None = True,
            period: int = 1) -> None:  # fmt: skip
        n = len(self.items)
        self.items.append(
            Event(
                event_id=f"{MID}-e{n:05d}",
                match_id=MID,
                period=period,
                t=float(n),  # type: ignore[arg-type]
                type=type_,
                team_id=team,
                player_id=f"{team}-p",
                x=x,
                y=34.0,
                end_x=None,
                end_y=None,
                outcome=outcome,
                receiver_id=None,
                ball_speed_ms=None,
            )  # fmt: skip
        )


def _match(events: list[Event], speeds: dict[str, list[float]] | None = None) -> MatchData:
    """`speeds`: per-player speed along x at each 0.1 s frame (period 1)."""
    speeds = speeds or {"h-p": [1.0] * 20, "a-p": [1.0] * 20}
    n = len(next(iter(speeds.values())))
    xs = {pid: 10.0 for pid in speeds}
    frames = []
    for k in range(n):
        players = []
        for pid, sp in speeds.items():
            if k > 0:
                xs[pid] += sp[k] * 0.1
            players.append(PlayerPos(player_id=pid, team_id=pid.split("-")[0], x=xs[pid],
                                     y=30.0, vx=sp[k], vy=0.0))  # fmt: skip
        frames.append(TrackingFrame(match_id=MID, frame=k, period=1, t=round(k * 0.1, 1),
                                    ball=(50.0, 34.0, 0.1), players=players))  # fmt: skip
    meta = MatchMeta(
        match_id=MID, seed=1, home=_club("h"), away=_club("a"),
        home_squad=[_player(p, "h") for p in speeds if p.startswith("h")],
        away_squad=[_player(p, "a") for p in speeds if p.startswith("a")],
        scenario_id="none", engine_version="test", stadium="S",
        kickoff_iso="2026-08-15T19:30:00-05:00", added_time_s=(0.0, 0.0),
    )  # fmt: skip
    return MatchData(meta=meta, events=events, frames=frames)


def _check(report: RealismReport, name: str) -> tuple[float, bool]:
    c = next(c for c in report.checks if c.name == name)
    return c.value, c.ok


def test_flags_out_of_range() -> None:
    ev = _Events()
    for _ in range(900):
        ev.add("pass", "h")
    for _ in range(500):
        ev.add("pass", "a", outcome=len(ev.items) % 5 != 0)
    report = validate_match(_match(ev.items))
    assert _check(report, "passes:h") == (900, False)
    assert _check(report, "passes:a") == (500, True)
    value, ok = _check(report, "pass_completion:a")
    assert value == pytest.approx(0.8, abs=0.01) and ok
    assert not report.ok


def test_possession_is_pass_share() -> None:
    ev = _Events()
    for _ in range(300):
        ev.add("pass", "h")
    for _ in range(100):
        ev.add("pass", "a")
    report = validate_match(_match(ev.items))
    assert _check(report, "possession:h")[0] == pytest.approx(0.75)
    assert _check(report, "possession:a") == (pytest.approx(0.25), False)


def test_shots_on_target_counts_goals_and_saves() -> None:
    ev = _Events()
    for _ in range(4):
        ev.add("shot", "h", outcome=False)
    ev.add("save", "a")
    ev.add("goal", "h")
    report = validate_match(_match(ev.items))
    assert _check(report, "shots:h")[0] == 4
    assert _check(report, "shots_on_target_ratio:h")[0] == pytest.approx(0.5)


def test_ppda_counts_opponent_build_up_against_high_actions() -> None:
    ev = _Events()
    # Period 1: home attacks right. Away passes in its own 60% (x > 42) vs home actions there.
    for _ in range(30):
        ev.add("pass", "a", x=80.0)
    for _ in range(10):
        ev.add("pass", "a", x=20.0)  # in the away team's attacking 40%: not counted
    for type_ in ("tackle", "interception", "foul"):
        ev.add(type_, "h", x=70.0)
    ev.add("tackle", "h", x=20.0)  # deep in home's own half: not counted
    assert _check(validate_match(_match(ev.items)), "ppda:h")[0] == pytest.approx(10.0)


def test_distance_speed_and_sprints_from_frames() -> None:
    sprinty = [5.0] * 600
    for start in (100, 300):
        sprinty[start : start + 15] = [8.0] * 15  # two sprints of 1.5 s
    sprinty[500:505] = [8.0] * 5  # 0.5 s: too short
    report = validate_match(_match([], {"h-p": sprinty, "a-p": [3.0] * 600}))
    dist = sum(sprinty[1:]) * 0.1 / 1000
    assert _check(report, "distance_km_outfield_player:h")[0] == pytest.approx(dist, rel=1e-6)
    assert _check(report, "top_speed_ms:h")[0] == pytest.approx(8.0)
    assert _check(report, "sprints_per_outfield_player:h")[0] == 2
    assert _check(report, "sprints_per_outfield_player:a")[0] == 0


def test_report_json_serializable() -> None:
    ev = _Events()
    ev.add("pass", "h")
    report = validate_match(_match(ev.items))
    back = RealismReport.model_validate(
        json.loads(json.dumps(report.model_dump(), allow_nan=False))
    )
    assert back == report
    assert {c.name.split(":")[0] for c in report.checks} >= set(RANGES) - {"goals_per_match"}


def test_validate_many_averages_and_checks_goals() -> None:
    reports = []
    for goals in (2, 3, 4):
        ev = _Events()
        for _ in range(goals):
            ev.add("goal", "h")
        reports.append(_match(ev.items))
    many = validate_many(reports)
    value, ok = _check(many, "goals_per_match")
    assert value == pytest.approx(3.0) and ok
    passes = next(c for c in many.checks if c.name == "passes")
    assert passes.value == 0 and not passes.ok and passes.in_range_share == 0.0
