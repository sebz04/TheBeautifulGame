"""Level-2 role targets: where a player wants to be, and how urgently.

Each role works in the team frame (attacking toward d = 105, own goal at (0, 34)) and
returns an absolute target plus an urgency in [0, 1] for `kinematics.step_player`.

`run_in_behind` waits `RUN_HOVER_M` onside of the offside line, then sprints behind it
once the run starts. The engine starts the run at the expected pass time minus the
runner's `timing_error_s` (`draw_timing_error`): an early release of about 0.5 s leaves
the runner offside when the ball is played.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np

from matchmind.engine.formations import to_team_frame
from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH

RoleName = Literal["mark", "press", "cover", "support", "run_in_behind", "hold_line", "gk_position"]

OWN_GOAL = np.array([0.0, PITCH_WIDTH / 2])  # team frame
HALFWAY = PITCH_LENGTH / 2
MARK_GOAL_SIDE_M = 1.5
PRESS_GOAL_SIDE_M = 1.0
COVER_SHARE = 0.35  # how far from the ball toward goal the cover point sits
SUPPORT_DIST_M = 12.0
SUPPORT_ANGLE_DEG = 50.0
GK_BASE_M, GK_PER_M, GK_MAX_M = 1.0, 0.08, 16.0
RUN_HOVER_M = 0.2  # how far onside a runner waits
RUN_DEPTH_M = 14.0  # how far behind the line the run aims
RUN_TIMING_SD_S = 0.35  # spread of release timing error (scaled by the Task 8.3 modifier)
LINE_BLOCK_SHIFT = 0.35
LINE_HEIGHT_RANGE_M = 16.0  # line_height 0 -> -8 m, 1 -> +8 m

URGENCY: dict[RoleName, float] = {
    "mark": 0.6,
    "press": 0.95,
    "cover": 0.5,
    "support": 0.5,
    "run_in_behind": 1.0,  # once started; 0.45 while waiting
    "hold_line": 0.7,
    "gk_position": 0.7,
}
RUN_WAIT_URGENCY = 0.45


@dataclass(frozen=True)
class RoleContext:
    """Absolute coordinates. Role-specific fields are optional."""

    pos: np.ndarray
    anchor: np.ndarray  # formation target
    ball: np.ndarray
    attacks_right: bool
    mark: np.ndarray | None = None  # opponent to mark
    line_depth: float | None = None  # own defensive line, team-frame depth (hold_line)
    offside_line: float | None = None  # absolute x of the opponents' offside line
    run_started: bool = False


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.hypot(*v))
    return v / n if n > 1e-9 else np.zeros(2)


def _clamp(p: np.ndarray) -> np.ndarray:
    return np.array([min(max(p[0], 0.0), PITCH_LENGTH), min(max(p[1], 0.0), PITCH_WIDTH)])


def defensive_line(anchors_depth: np.ndarray, ball_depth: float, line_height: float) -> float:
    """Team-frame depth the back line holds: anchors shifted with the ball and the club's
    line height, never ahead of the ball, never inside the goal."""
    line = (
        float(np.mean(anchors_depth))
        + LINE_BLOCK_SHIFT * (ball_depth - HALFWAY)
        + (line_height - 0.5) * LINE_HEIGHT_RANGE_M
    )
    return max(min(line, ball_depth - 2.0), 1.0)


def offside_line(opponents: np.ndarray, ball: np.ndarray, attacks_right: bool) -> float:
    """Absolute x of the offside line: the deeper of the second-last opponent and the
    ball, never in the attackers' own half."""
    depths = sorted((float(d) for d in to_team_frame(opponents, attacks_right)[:, 0]),
                    reverse=True)  # fmt: skip
    second_last = depths[1] if len(depths) > 1 else 0.0
    ball_depth = float(to_team_frame(ball, attacks_right)[0])
    depth = max(second_last, ball_depth, HALFWAY)
    return depth if attacks_right else PITCH_LENGTH - depth


def draw_timing_error(rng: np.random.Generator, scale: float = 1.0) -> float:
    """Seconds a runner releases early (positive) or late (negative)."""
    return float(rng.normal(0.0, RUN_TIMING_SD_S * scale))


def role_target(role: RoleName, ctx: RoleContext) -> tuple[np.ndarray, float]:
    def team(p: np.ndarray) -> np.ndarray:
        return to_team_frame(np.asarray(p, dtype=float), ctx.attacks_right)

    pos, anchor, ball = team(ctx.pos), team(ctx.anchor), team(ctx.ball)
    urgency = URGENCY[role]
    if role == "press":
        local = ball + PRESS_GOAL_SIDE_M * _unit(OWN_GOAL - ball)
    elif role == "mark":
        if ctx.mark is None:
            raise ValueError("mark needs ctx.mark (the opponent's position)")
        opp = team(ctx.mark)
        local = opp + MARK_GOAL_SIDE_M * _unit(OWN_GOAL - opp)
    elif role == "cover":
        point = ball + COVER_SHARE * (OWN_GOAL - ball)
        local = 0.5 * point + 0.5 * anchor
    elif role == "support":
        side = -1.0 if anchor[1] < ball[1] else 1.0
        angle = np.radians(SUPPORT_ANGLE_DEG)
        local = ball + SUPPORT_DIST_M * np.array([np.cos(angle), side * np.sin(angle)])
    elif role == "gk_position":
        dist = float(np.hypot(*(ball - OWN_GOAL)))
        depth = min(max(GK_BASE_M + GK_PER_M * dist, GK_BASE_M), GK_MAX_M)
        local = OWN_GOAL + depth * _unit(ball - OWN_GOAL)
    elif role == "hold_line":
        if ctx.line_depth is None:
            raise ValueError("hold_line needs ctx.line_depth")
        local = np.array([ctx.line_depth, anchor[1]])
    else:  # run_in_behind
        if ctx.offside_line is None:
            raise ValueError("run_in_behind needs ctx.offside_line")
        line = float(team(np.array([ctx.offside_line, 0.0]))[0])
        if ctx.run_started:
            local = np.array([line + RUN_DEPTH_M, pos[1]])
        else:
            local = np.array([line - RUN_HOVER_M, pos[1]])
            urgency = RUN_WAIT_URGENCY
    return _clamp(team(local)), urgency
