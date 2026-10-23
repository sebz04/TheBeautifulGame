"""Level-4 tactics: phase shapes, pressing triggers, and how often forwards run in behind.

`formation_shape` moves the formation anchors (team frame, attacking toward d = 105) for
each phase of play: deeper and narrower in a block, higher and wider in build-up. With
10 or 9 players the most advanced outfield slots go first (the widest of a line), and
each line is re-spaced. Pressing triggers (a back pass, a poor touch, a receiver facing
his own goal) tell a team when to press. `runs_in_behind_rate` is a team tactic, so it
is not limited by the subtle modifier cap; offsides are never set directly, they come
from runs x timing x the opponent's line.
"""

from functools import cache
from typing import Literal, get_args

import numpy as np

from matchmind.engine import constants as C
from matchmind.engine.formations import MAX_LINE_SPACING, formation_anchors
from matchmind.engine.lineup import FORMATION_LINES
from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH
from matchmind.schemas import Event, TrackingFrame
from matchmind.schemas_profile import ClubProfile, Position

Phase = Literal["build_up", "mid_block", "low_block", "counter", "high_press", "set_piece"]
PHASES: tuple[Phase, ...] = get_args(Phase)
CENTRE_W = PITCH_WIDTH / 2


def _lines(formation: str) -> list[Position]:
    df, mf, fw = FORMATION_LINES[formation]
    lines: list[Position] = ["GK"]
    return lines + ["DF"] * df + ["MF"] * mf + ["FW"] * fw


@cache
def _kept(formation: str, n_players: int) -> tuple[int, ...]:
    """Anchor rows kept with `n_players` on the pitch: drop the most advanced outfield
    slots first, the widest of a line before its centre."""
    if not 7 <= n_players <= 11:
        raise ValueError(f"n_players must be 7-11, got {n_players}")
    a = formation_anchors(formation)
    order = sorted(range(1, 11), key=lambda i: (a[i, 0], abs(a[i, 1] - CENTRE_W), i))
    dropped = set(order[::-1][: 11 - n_players])
    return tuple(i for i in range(11) if i not in dropped)


def shape_lines(formation: str, n_players: int = 11) -> list[Position]:
    """The line (GK, DF, MF, FW) of each row of `formation_shape`."""
    lines = _lines(formation)
    return [lines[i] for i in _kept(formation, n_players)]


@cache
def _base(formation: str, n_players: int) -> np.ndarray:
    a = formation_anchors(formation)[list(_kept(formation, n_players))]
    for depth in np.unique(a[1:, 0]):
        rows = np.flatnonzero(np.isclose(a[:, 0], depth))
        rows = rows[rows > 0]
        m = len(rows)
        spacing = min(MAX_LINE_SPACING, (PITCH_WIDTH - 12) / max(m - 1, 1))
        a[rows, 1] = CENTRE_W + (np.arange(m) - (m - 1) / 2) * spacing
    return a


def formation_shape(formation: str, phase: Phase, n_players: int = 11) -> np.ndarray:
    """(n_players, 2) target spots (d, w) in the team frame, keeper first."""
    offset, depth_scale, width_scale, gk_depth = C.PHASE_SHAPE[phase]
    a = _base(formation, n_players).copy()
    a[1:, 0] = C.SHAPE_PIVOT_M + (a[1:, 0] - C.SHAPE_PIVOT_M) * depth_scale + offset
    a[1:, 1] = CENTRE_W + (a[1:, 1] - CENTRE_W) * width_scale
    a[0] = (gk_depth, CENTRE_W)
    a[:, 0] = np.clip(a[:, 0], 1.0, PITCH_LENGTH - 1.0)
    a[:, 1] = np.clip(a[:, 1], 1.0, PITCH_WIDTH - 1.0)
    return a


def trigger(back_pass: bool, poor_touch: bool, facing_own_goal: bool) -> bool:
    return back_pass or poor_touch or facing_own_goal


def pressing_trigger(
    last_event: Event | None, frame: TrackingFrame, pressing_team: str, attacks_right: bool
) -> bool:
    """Should `pressing_team` (attacking right if `attacks_right`) press now?

    Yes after an opponent's back pass (losing `BACK_PASS_M` of depth, ending in his last
    `BACK_PASS_ZONE_M`) or poor touch
    (`extras.heavy_touch`), or when the opponent nearest the ball is moving toward his
    own goal.
    """
    if last_event is None or last_event.team_id == pressing_team:
        back = poor = False
    else:
        sign = -1.0 if attacks_right else 1.0  # the opponent's attacking direction
        end_x = last_event.end_x if last_event.end_x is not None else last_event.x
        end_depth = end_x if sign > 0 else PITCH_LENGTH - end_x  # from his own goal
        back = (last_event.type == "pass" and sign * (end_x - last_event.x) < -C.BACK_PASS_M
                and end_depth <= C.BACK_PASS_ZONE_M)  # fmt: skip
        poor = bool(last_event.extras.get("heavy_touch"))
    opponents = [p for p in frame.players if p.team_id != pressing_team]
    facing = False
    if opponents:
        bx, by = frame.ball[0], frame.ball[1]
        carrier = min(opponents, key=lambda p: (p.x - bx) ** 2 + (p.y - by) ** 2)
        toward_own = carrier.vx if attacks_right else -carrier.vx  # own goal is behind him
        facing = toward_own > C.FACING_OWN_GOAL_MS
    return trigger(back, poor, facing)


def runs_in_behind_rate(
    club: ClubProfile, role: str | None, opponent_line_height: float, pace: float = 0.5
) -> float:
    """Runs per minute in possession: more for direct, high-tempo teams, runner roles,
    pace, and a high opponent line (more space behind it). `role=None` is neutral."""
    t = club.tactical_identity
    role_factor = 1.0 if role is None else C.ROLE_RUN_FACTOR.get(role, C.OTHER_ROLE_RUN_FACTOR)
    return (
        C.RUN_RATE_BASE
        * (0.5 + t.directness)
        * (0.7 + 0.6 * t.tempo)
        * role_factor
        * (0.7 + 0.6 * pace)
        * (0.5 + opponent_line_height)
    )
