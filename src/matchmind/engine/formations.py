"""Formation anchors in the team frame: depth `d` from the team's own goal line, width `w`.

The team frame attacks towards d = 105. Anchors are the shape with the ball at the
centre spot; the engine shifts them toward the ball.
"""

import numpy as np

from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH

GK_DEPTH = 5.0
BACK_LINE_DEPTH = 30.0
FRONT_LINE_DEPTH = 62.0
MAX_LINE_SPACING = 16.0


def formation_anchors(formation: str) -> np.ndarray:
    """(11, 2) array of (d, w): GK first, then each line from back to front.

    Line order matches `lineup.starting_xi` (GK, DF, MF, FW), so player i takes anchor i.
    """
    lines = [int(n) for n in formation.split("-")]
    if sum(lines) != 10:
        raise ValueError(f"formation must have 10 outfield players: {formation!r}")
    centre = PITCH_WIDTH / 2
    anchors = [(GK_DEPTH, centre)]
    for j, n in enumerate(lines):
        depth = BACK_LINE_DEPTH + j * (FRONT_LINE_DEPTH - BACK_LINE_DEPTH) / (len(lines) - 1)
        spacing = min(MAX_LINE_SPACING, (PITCH_WIDTH - 12) / max(n - 1, 1))
        for i in range(n):
            anchors.append((depth, centre + (i - (n - 1) / 2) * spacing))
    return np.array(anchors, dtype=float)


def to_team_frame(xy: np.ndarray, attacks_right: bool) -> np.ndarray:
    """Absolute pitch coordinates <-> team frame (the transform is its own inverse)."""
    if attacks_right:
        return xy.copy()
    mirrored: np.ndarray = np.array([PITCH_LENGTH, PITCH_WIDTH]) - xy
    return mirrored
