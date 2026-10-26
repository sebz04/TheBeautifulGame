"""Sliding-window limits for live agent runs: 5 an hour per visitor, 100 a day in all.

The limits bound what a public demo can spend on the model (Azure for Students credit).
State is in memory, so it resets when the API restarts, and each replica counts
separately (the demo runs one).
"""

import math
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

PER_IP, PER_IP_WINDOW_S = 5, 3600.0
GLOBAL, GLOBAL_WINDOW_S = 100, 86400.0


class RateLimiter:
    def __init__(
        self,
        per_ip: int = PER_IP,
        global_: int = GLOBAL,
        *,
        per_ip_window_s: float = PER_IP_WINDOW_S,
        global_window_s: float = GLOBAL_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.per_ip, self.global_ = per_ip, global_
        self.per_ip_window_s, self.global_window_s = per_ip_window_s, global_window_s
        self.clock = clock
        self._ip: dict[str, deque[float]] = {}
        self._all: deque[float] = deque()

    @staticmethod
    def _wait(hits: deque[float], limit: int, window: float, now: float) -> float | None:
        while hits and hits[0] <= now - window:
            hits.popleft()
        return hits[0] + window - now if len(hits) >= limit else None

    def hit(self, ip: str) -> int | None:
        """Count a call from ``ip``; or, over a limit, the seconds until one is free."""
        now = self.clock()
        mine = self._ip.setdefault(ip, deque())
        waits = [
            w
            for w in (
                self._wait(mine, self.per_ip, self.per_ip_window_s, now),
                self._wait(self._all, self.global_, self.global_window_s, now),
            )
            if w is not None
        ]
        if waits:
            return max(1, math.ceil(max(waits)))
        mine.append(now)
        self._all.append(now)
        return None


def client_ip(request: Request) -> str:
    """The rightmost ``X-Forwarded-For`` entry (added by the trusted ingress, unlike the
    entries a caller can send), else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"
