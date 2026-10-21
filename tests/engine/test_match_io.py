from pathlib import Path

from matchmind.engine.match_io import read_match, write_match
from matchmind.schemas import (
    Club,
    Event,
    MatchData,
    MatchMeta,
    Player,
    PlayerPos,
    TrackingFrame,
)


def _club(cid: str) -> Club:
    return Club(
        club_id=cid,
        name=cid.title(),
        short=cid[:3].upper(),
        primary_color="#000000",
        secondary_color="#FFFFFF",
        formation="4-3-3",
    )


def _player(pid: str, cid: str) -> Player:
    return Player(
        player_id=pid, name=pid, club_id=cid, number=9, position="FW", pace=0.5, skill=0.6,
        stamina=0.4,
    )  # fmt: skip


def _data() -> MatchData:
    meta = MatchMeta(
        match_id="r01-a-v-b",
        seed=3,
        home=_club("aaa"),
        away=_club("bbb"),
        home_squad=[_player("aaa-01", "aaa")],
        away_squad=[_player("bbb-01", "bbb")],
        scenario_id="none",
        engine_version="test",
        stadium="Estadio X",
        kickoff_iso="2026-08-15T19:00:00-05:00",
        added_time_s=(120.0, 240.0),
    )
    events = [
        Event(
            event_id="r01-a-v-b-e00000", match_id="r01-a-v-b", period=1, t=0.0, type="kickoff",
            team_id="aaa", player_id="aaa-01", x=52.5, y=34.0, end_x=45.0, end_y=30.0,
            outcome=True, receiver_id="aaa-01", ball_speed_ms=10.0, extras={"flight_s": 0.8},
        ),
        Event(
            event_id="r01-a-v-b-e00001", match_id="r01-a-v-b", period=2, t=12.3, type="shot",
            team_id="bbb", player_id="bbb-01", x=90.1, y=30.25, end_x=None, end_y=None,
            outcome=None, receiver_id=None, ball_speed_ms=None,
        ),
    ]  # fmt: skip
    frames = [
        TrackingFrame(
            match_id="r01-a-v-b",
            frame=i,
            period=1,
            t=round(i * 0.1, 1),
            ball=(52.5, 34.0, 0.1 * i),
            players=[
                PlayerPos(player_id="aaa-01", team_id="aaa", x=50.0 + i, y=30.0, vx=1.5, vy=0.0),
                PlayerPos(player_id="bbb-01", team_id="bbb", x=60.0, y=31.0 - i, vx=0.0, vy=-2.0),
            ],
        )
        for i in range(3)
    ]
    return MatchData(meta=meta, events=events, frames=frames)


def test_round_trip_is_identical(tmp_path: Path) -> None:
    data = _data()
    write_match(data, tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {"meta.json", "events.parquet", "frames.parquet"}
    assert read_match(tmp_path) == data


def test_write_is_byte_identical(tmp_path: Path) -> None:
    write_match(_data(), tmp_path / "a")
    write_match(_data(), tmp_path / "b")
    for name in ("meta.json", "events.parquet", "frames.parquet"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_round_trip_with_no_events(tmp_path: Path) -> None:
    data = _data().model_copy(update={"events": []})
    write_match(data, tmp_path)
    assert read_match(tmp_path) == data
