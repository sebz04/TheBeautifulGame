"""The live replay: one SSE stream of frames, events, cues, and insights (plan Task 21).

Every message of a match has a fixed place in one ordering (by period, t, then frame,
event, cue, insight), and ``seq`` is that place, so ids are the same on every connection:
``id = "{period}:{t:.1f}:{seq}"``. A reconnect with ``Last-Event-ID`` continues after that
seq; ``from_t`` starts at the first message at or after (period, from_t). Messages are
paced on the match clock at ``speed`` (0 = as fast as possible). Cues are the fast lane:
precomputed, sent at their ``t_in``, independent of the agents.
"""

from __future__ import annotations

import asyncio
import bisect
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from sse_starlette import EventSourceResponse

from matchmind.api.services import Services, Svc
from matchmind.mcp_server.server import _compact
from matchmind.schemas import MatchMeta, TrackingFrame

router = APIRouter(prefix="/api")

Kind = Literal["frame", "event", "cue", "insight"]
ORDER: dict[Kind, int] = {"frame": 0, "event": 1, "cue": 2, "insight": 3}
FRAME_EVERY = 2  # 10 Hz tracking sent at 5 Hz
CHUNK_S = 20.0  # frames are read from the store this many seconds at a time
PING_S = 15


@dataclass(frozen=True, order=True)
class Entry:
    period: int
    t: float
    order: int
    key: str  # frame number, event id, cue id, or insight id


@dataclass
class ReplayIndex:
    entries: list[Entry]
    first_half_s: float  # match clock: period 2 starts after this many seconds

    def clock(self, period: int, t: float) -> float:
        return t if period == 1 else self.first_half_s + t

    def start(self, period: int, from_t: float) -> int:
        return bisect.bisect_left(self.entries, (period, from_t), key=lambda e: (e.period, e.t))


def build_index(svc: Services, meta: MatchMeta) -> ReplayIndex:
    mid = meta.match_id
    times = svc.store.frame_times(mid) if svc.store.exists(mid) else []
    entries = [Entry(p, round(t, 1), ORDER["frame"], str(f)) for f, p, t in times
               if f % FRAME_EVERY == 0]  # fmt: skip
    entries += [Entry(e.period, round(e.t, 1), ORDER["event"], e.event_id)
                for e in svc.events(mid)]  # fmt: skip
    entries += [Entry(c.period, round(c.t_in, 1), ORDER["cue"], c.cue_id)
                for c in svc.repo.list_cues(mid)]  # fmt: skip
    moments = {m.moment_id: m for m in svc.repo.list_moments(mid)}
    entries += [Entry(m.period, round(m.t_end, 1), ORDER["insight"], i.insight_id)
                for i in svc.repo.list_insights(mid)
                if i.verified and (m := moments.get(i.moment_id))]  # fmt: skip
    entries.sort()
    first = [t for _, p, t in times if p == 1]
    return ReplayIndex(entries, (max(first) + 0.1) if first else 45 * 60.0)


def _frame(f: TrackingFrame) -> dict[str, Any]:
    return {
        "frame": f.frame, "period": f.period, "t": f.t,
        "ball": [round(v, 2) for v in f.ball],
        "players": [{"player_id": p.player_id, "team_id": p.team_id,
                     "x": round(p.x, 2), "y": round(p.y, 2)} for p in f.players],
    }  # fmt: skip


class _Payloads:
    """Message bodies, with frames read from the store a chunk at a time."""

    def __init__(self, svc: Services, meta: MatchMeta) -> None:
        mid = meta.match_id
        self.svc, self.mid = svc, mid
        self.events = {e.event_id: e for e in svc.events(mid)}
        self.cues = {c.cue_id: c for c in svc.repo.list_cues(mid)}
        self.insights = {i.insight_id: i for i in svc.repo.list_insights(mid)}
        self.lines = svc.repo.list_live_lines(mid)
        self.frames: dict[int, TrackingFrame] = {}

    def body(self, e: Entry) -> tuple[Kind, dict[str, Any]]:
        if e.order == ORDER["frame"]:
            n = int(e.key)
            if n not in self.frames:
                chunk = self.svc.store.read_window(self.mid, e.period, e.t, e.t + CHUNK_S)
                self.frames = {f.frame: f for f in chunk}
            return "frame", _frame(self.frames[n])
        if e.order == ORDER["event"]:
            return "event", _compact(self.events[e.key])
        if e.order == ORDER["cue"]:
            return "cue", self.cues[e.key].model_dump()
        ins = self.insights[e.key]
        return "insight", {
            "insight_id": ins.insight_id, "moment_id": ins.moment_id, "level": ins.level,
            "headline": ins.headline, "source": ins.source,
            "live_line": self.lines.get(ins.insight_id),
        }  # fmt: skip


def _last_seq(last_event_id: str | None) -> int | None:
    if not last_event_id:
        return None
    try:
        return int(last_event_id.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        raise HTTPException(422, f"bad Last-Event-ID {last_event_id!r}") from None


async def _stream(
    svc: Services, meta: MatchMeta, index: ReplayIndex, start: int, speed: float
) -> AsyncIterator[dict[str, str]]:
    payloads = _Payloads(svc, meta)
    began = time.monotonic()
    clock0: float | None = None
    for seq in range(start, len(index.entries)):
        e = index.entries[seq]
        now = index.clock(e.period, e.t)
        clock0 = now if clock0 is None else clock0
        if speed > 0:
            delay = (now - clock0) / speed - (time.monotonic() - began)
            if delay > 0:
                await asyncio.sleep(delay)
        elif seq % 200 == 0:
            await asyncio.sleep(0)  # let the server notice a disconnect
        kind, body = payloads.body(e)
        yield {"id": f"{e.period}:{e.t:.1f}:{seq}", "event": kind, "data": json.dumps(body)}
    last = index.entries[-1] if index.entries else Entry(2, 0.0, 0, "")
    yield {"id": f"{last.period}:{last.t:.1f}:{len(index.entries)}", "event": "end",
           "data": json.dumps({"match_id": meta.match_id})}  # fmt: skip


@router.get("/matches/{match_id}/live")
async def live(
    match_id: str,
    svc: Svc,
    period: Annotated[int, Query(ge=1, le=2)] = 1,
    from_t: Annotated[float, Query(ge=0)] = 0.0,
    speed: Annotated[float, Query(ge=0, le=32)] = 1.0,
    last_event_id: Annotated[str | None, Header()] = None,
) -> EventSourceResponse:
    meta = svc.meta(match_id)
    index = svc.replay_index(meta, build_index)
    last = _last_seq(last_event_id)
    start = last + 1 if last is not None else index.start(period, from_t)
    return EventSourceResponse(_stream(svc, meta, index, start, speed), ping=PING_S)
