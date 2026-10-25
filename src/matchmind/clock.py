"""Match clock: seconds within a period to the minute fans read ("56'", "45+2'").

Football counts the minute being played, so 55:38 elapsed is the 56th minute. Time past
45:00 in a period is stoppage time ("45+1'", "90+3'").
"""

from __future__ import annotations

from matchmind.schemas import Period

HALF_S = 45 * 60


def _parts(period: Period, t: float) -> tuple[int, int]:
    """(regular minute, stoppage minute), e.g. (45, 2) for 45+2'."""
    base = 45 * (period - 1)
    if t < HALF_S:
        return base + int(t // 60) + 1, 0
    return base + 45, int((t - HALF_S) // 60) + 1


def minute_label(period: Period, t: float) -> str:
    regular, added = _parts(period, t)
    return f"{regular}+{added}'" if added else f"{regular}'"


def match_minute(period: Period, t: float) -> int:
    """The minute as one number, stoppage added (45+2' is 47), as the number checker reads it."""
    regular, added = _parts(period, t)
    return regular + added
