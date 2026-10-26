"""TASK-21.2: the SSE live replay (order, resume, seek, fast-lane timing)."""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

Built = Any  # tests/api/conftest.py's Built


@dataclass
class Msg:
    id: str
    type: str
    data: dict[str, Any]
    arrived: float

    @property
    def seq(self) -> int:
        return int(self.id.rsplit(":", 1)[1])

    @property
    def when(self) -> tuple[int, float]:
        period, t, _ = self.id.split(":")
        return int(period), float(t)


def _read(
    client: TestClient,
    url: str,
    *,
    stop: Callable[[Msg], bool] = lambda m: False,
    limit: int = 100_000,
    headers: dict[str, str] | None = None,
) -> list[Msg]:
    """Messages until ``stop`` (that message excluded), ``limit``, or the end."""
    out: list[Msg] = []
    cur: dict[str, str] = {}
    with client.stream("GET", url, headers=headers) as resp:
        assert resp.status_code == 200, resp.read()
        for line in resp.iter_lines():
            if line:
                key, _, value = line.partition(":")
                cur[key] = value.removeprefix(" ")
                continue
            if "id" not in cur:  # a ping comment
                cur = {}
                continue
            msg = Msg(cur["id"], cur["event"], json.loads(cur["data"]), time.monotonic())
            cur = {}
            if stop(msg):
                break
            out.append(msg)
            if msg.type == "end" or len(out) >= limit:
                break
    return out


def _url(built: Built, **params: Any) -> str:
    query = "&".join(f"{k}={v}" for k, v in ({"speed": 0} | params).items())
    return f"/api/matches/{built.meta.match_id}/live?{query}"


def _contiguous(msgs: list[Msg]) -> bool:
    seqs = [m.seq for m in msgs]
    return seqs == list(range(seqs[0], seqs[0] + len(seqs)))


def test_sse_order_and_types(client: TestClient, built: Built) -> None:
    msgs = _read(client, _url(built), stop=lambda m: m.when >= (1, 60.0))
    assert {"frame", "event", "cue"} <= {m.type for m in msgs}
    assert _contiguous(msgs) and msgs[0].seq == 0
    assert [m.when for m in msgs] == sorted(m.when for m in msgs)
    frames = [m for m in msgs if m.type == "frame" and m.when < (1, 10.0)]
    assert 48 <= len(frames) <= 51  # 5 Hz
    frame = frames[0].data
    assert set(frame) == {"frame", "period", "t", "ball", "players"}
    assert {"player_id", "team_id", "x", "y"} == set(frame["players"][0])
    event = next(m.data for m in msgs if m.type == "event")
    assert "best_score" not in event["extras"]  # decision scoring stays out of the stream


def test_sse_resume_no_duplicates(client: TestClient, built: Built) -> None:
    first = _read(client, _url(built), stop=lambda m: m.when >= (1, 120.0))
    again = _read(client, _url(built, period=1, from_t=120), limit=50)
    assert again[0].seq == first[-1].seq + 1
    assert _contiguous(first + again)


def test_sse_resume_with_last_event_id(client: TestClient, built: Built) -> None:
    first = _read(client, _url(built, period=1, from_t=300), limit=400)
    again = _read(client, _url(built), headers={"Last-Event-ID": first[-1].id}, limit=50)
    assert _contiguous(first + again)


def test_sse_seek_backwards(client: TestClient, built: Built) -> None:
    ahead = _read(client, _url(built), stop=lambda m: m.when >= (1, 120.0))
    back = _read(client, _url(built, period=1, from_t=30), limit=20)
    first_at_30 = next(m for m in ahead if m.when >= (1, 30.0))
    assert back[0].id == first_at_30.id  # the same stream, replayed from 30 s


def test_sse_insight_at_its_moment_and_end(client: TestClient, built: Built) -> None:
    moment = built.repo.get_moment(built.insight.moment_id)
    start = max(0.0, moment.t_end - 2)
    msgs = _read(client, _url(built, period=moment.period, from_t=start),
                 stop=lambda m: m.type == "insight")  # fmt: skip
    rest = _read(client, _url(built, period=moment.period, from_t=start),
                 limit=len(msgs) + 1)  # fmt: skip
    insight = rest[-1]
    assert insight.type == "insight" and insight.when == (moment.period, round(moment.t_end, 1))
    assert insight.data["insight_id"] == built.insight.insight_id and insight.data["headline"]
    last = built.store.frame_times(built.meta.match_id)[-1]
    tail = _read(client, _url(built, period=2, from_t=last[2] - 1))
    assert tail[-1].type == "end"


def test_fast_lane_cue_timing(client: TestClient, built: Built) -> None:
    """At speed 1, a cue arrives within 1 s of its t_in on the replay clock."""
    cue = next(c for c in built.repo.list_cues(built.meta.match_id) if c.t_in > 120)
    start = cue.t_in - 2.0
    msgs = _read(client, _url(built, period=cue.period, from_t=start, speed=1),
                 stop=lambda m: m.type == "cue" and m.data["cue_id"] == cue.cue_id)  # fmt: skip
    began = msgs[0].arrived - (msgs[0].when[1] - start)
    elapsed = time.monotonic() - began
    assert abs(elapsed - (cue.t_in - start)) < 1.0


def test_live_bad_params(client: TestClient, built: Built) -> None:
    assert client.get(_url(built, speed=-1)).status_code == 422
    assert client.get(_url(built, period=3)).status_code == 422
    assert client.get("/api/matches/nope/live").status_code == 404
