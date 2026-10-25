"""Speed and running: ball and shot speed, a player's motion from frames, and alert cues.

Distance is the sum of position steps within each period; speed is the frame velocity;
a sprint is above `sprint_ms` for at least `sprint_min_s` (the realism definitions).
`alerts` turns frames into overlay cues: a `speed_alert` plus a `name_tag` the moment a
run becomes a sprint (once per run), and a `distance_alert` each time a player passes
another `distance_step_m`. Times are (period, t) pairs, since `t` restarts each half.
"""

import math
from collections.abc import Iterable

from pydantic import BaseModel

from matchmind.engine.coupled import Motion
from matchmind.engine.realism_ranges import SPRINT_MIN_S, SPRINT_SPEED_MS
from matchmind.schemas import CueKind, Event, OverlayCue, TrackingFrame

DT = 0.1
CUE_S = 4.0  # how long a cue stays on screen
PRIORITY: dict[str, int] = {"name_tag": 3, "speed_alert": 2, "distance_alert": 1}
MatchTime = tuple[int, float]


class AlertThresholds(BaseModel):
    sprint_ms: float = SPRINT_SPEED_MS
    sprint_min_s: float = SPRINT_MIN_S
    distance_step_m: float = 1000.0


def ball_speed(event: Event) -> float | None:
    """The kick speed, or the average speed over the flight (end point / `arrival_t`)."""
    if event.ball_speed_ms is not None:
        return event.ball_speed_ms
    raw = event.extras.get("arrival_t")
    if raw is None or event.end_x is None or event.end_y is None or float(raw) <= event.t:
        return None
    return math.hypot(event.end_x - event.x, event.end_y - event.y) / (float(raw) - event.t)


def shot_speed_kmh(event: Event) -> float:
    speed = ball_speed(event)
    if speed is None:
        raise ValueError(f"event {event.event_id} has no ball speed")
    return speed * 3.6


def _upto(frames: Iterable[TrackingFrame], t_to: MatchTime) -> Iterable[TrackingFrame]:
    return (f for f in frames if (f.period, f.t) <= t_to)


def player_motion(frames: Iterable[TrackingFrame], player_id: str, t_to: MatchTime,
                  thresholds: AlertThresholds | None = None) -> Motion:  # fmt: skip
    """Distance, top speed, sprints, and minutes on the pitch up to (period, t)."""
    th = thresholds or AlertThresholds()
    need = round(th.sprint_min_s / DT)
    m = Motion()
    last: tuple[int, float, float] | None = None  # (period, x, y)
    run = 0
    for f in _upto(frames, t_to):
        p = next((p for p in f.players if p.player_id == player_id), None)
        if p is None:
            continue
        if last is not None and last[0] == f.period:
            m.distance_m += math.hypot(p.x - last[1], p.y - last[2])
        elif last is not None:  # a new period: a run cannot carry over
            m.sprints += run >= need
            run = 0
        last = (f.period, p.x, p.y)
        speed = math.hypot(p.vx, p.vy)
        m.top_speed_ms = max(m.top_speed_ms, speed)
        if speed > th.sprint_ms:
            run += 1
        else:
            m.sprints += run >= need
            run = 0
        m.minutes += DT / 60.0
    m.sprints += run >= need
    return m


def _cue(f: TrackingFrame, kind: CueKind, player_id: str, payload: dict[str, object]) -> OverlayCue:
    return OverlayCue(
        cue_id=f"{f.match_id}-{kind}-{player_id}-{f.period}-{f.t:.1f}",
        match_id=f.match_id,
        period=f.period,
        t_in=f.t,
        t_out=round(f.t + CUE_S, 1),
        kind=kind,
        priority=PRIORITY[kind],
        payload=payload,
    )


def alerts(frames: Iterable[TrackingFrame], t: MatchTime,
           thresholds: AlertThresholds | None = None) -> list[OverlayCue]:  # fmt: skip
    """Every cue triggered up to (period, t), in time order."""
    th = thresholds or AlertThresholds()
    need = round(th.sprint_min_s / DT)
    run: dict[str, int] = {}
    dist: dict[str, float] = {}
    last: dict[str, tuple[int, float, float]] = {}
    cues: list[OverlayCue] = []
    for f in _upto(frames, t):
        for p in f.players:
            pid = p.player_id
            prev = last.get(pid)
            if prev is not None and prev[0] == f.period:
                before = dist.get(pid, 0.0)
                dist[pid] = before + math.hypot(p.x - prev[1], p.y - prev[2])
                passed = int(dist[pid] // th.distance_step_m) - int(before // th.distance_step_m)
                for k in range(passed):
                    step = (int(before // th.distance_step_m) + k + 1) * th.distance_step_m
                    cues.append(_cue(f, "distance_alert", pid,
                                     {"player_id": pid, "distance_m": round(step)}))  # fmt: skip
            elif prev is not None:
                run[pid] = 0
            last[pid] = (f.period, p.x, p.y)
            speed = math.hypot(p.vx, p.vy)
            run[pid] = run.get(pid, 0) + 1 if speed > th.sprint_ms else 0
            if run[pid] == need:
                payload = {"player_id": pid, "speed_ms": round(speed, 2)}
                cues.append(_cue(f, "speed_alert", pid, payload))
                cues.append(_cue(f, "name_tag", pid, {"player_id": pid}))
    return cues
