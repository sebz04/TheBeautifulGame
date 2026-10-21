"""Pitch coordinates: 105 x 68 m, origin at the bottom-left corner."""

import math

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0


def clamp_to_pitch(x: float, y: float) -> tuple[float, float]:
    return min(max(x, 0.0), PITCH_LENGTH), min(max(y, 0.0), PITCH_WIDTH)


def zone_index(x: float, y: float, nx: int = 16, ny: int = 12) -> tuple[int, int]:
    """Grid cell (column along the length, row across the width) for a point.

    Points on or beyond an edge map to the nearest cell inside the grid.
    """
    cx, cy = clamp_to_pitch(x, y)
    ix = min(int(cx / PITCH_LENGTH * nx), nx - 1)
    iy = min(int(cy / PITCH_WIDTH * ny), ny - 1)
    return ix, iy


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])
