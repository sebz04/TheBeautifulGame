"""Pitch control: the probability the attacking team wins the ball if it is played to a point.

A vectorized NumPy version of Spearman (2018), "Beyond Expected Goals", following the
Friends of Tracking implementation by Laurie Shaw (LaurieOnTracking,
`Metrica_PitchControl.py`, MIT License, Copyright (c) 2021 Friends-of-Tracking-Data-FoTD).
Same model and defaults: each player reacts for `reaction_time` on their current
velocity, then runs at `max_player_speed`; arrival times are uncertain (logistic,
`tti_sigma`); control accrues at rate `lambda` until the ball is controlled. When the
attacking direction is given, offside attackers are dropped first (the reference's
`check_offsides` rule, see `offside_players`). All targets are integrated at once; each
target stops at the step where the reference loop would stop, so results match it
(checked in tests).
"""

import math
from collections.abc import Collection

import numpy as np
from pydantic import BaseModel

from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH
from matchmind.schemas import TrackingFrame


class PCParams(BaseModel):
    max_player_speed: float = 5.0  # m/s
    reaction_time: float = 0.7  # s
    tti_sigma: float = 0.45  # s, spread of arrival time
    lambda_att: float = 4.3  # control rate, attacking team (1/s)
    kappa_def: float = 1.0  # defending advantage (1 = none)
    gk_factor: float = 3.0  # keepers control the ball faster (they can catch it)
    average_ball_speed: float = 15.0  # m/s
    int_dt: float = 0.04  # s, integration step
    max_int_time: float = 10.0  # s
    model_converge_tol: float = 0.01
    time_to_control_veto: float = 3.0  # ignore players with < 10^-3 chance of mattering

    @property
    def lambda_def(self) -> float:
        return self.lambda_att * self.kappa_def

    def time_to_control(self, lam: float) -> float:
        return (
            self.time_to_control_veto
            * math.log(10)
            * (math.sqrt(3) * self.tti_sigma / math.pi + 1 / lam)
        )


def offside_players(
    frame: TrackingFrame, attacking_team: str, attacks_right: bool, tol: float = 0.2
) -> set[str]:
    """Attackers beyond max(second-last defender, ball, halfway line) + `tol`.

    Depth is measured along the attacking direction from the halfway line. Simple rule:
    no "interfering with play" judgement.
    """
    sign = 1.0 if attacks_right else -1.0

    def depth(x: float) -> float:
        return sign * (x - PITCH_LENGTH / 2)

    defenders = sorted((depth(p.x) for p in frame.players if p.team_id != attacking_team),
                       reverse=True)  # fmt: skip
    second_last = defenders[1] if len(defenders) > 1 else -math.inf
    line = max(second_last, depth(frame.ball[0]), 0.0) + tol
    return {p.player_id for p in frame.players
            if p.team_id == attacking_team and depth(p.x) > line}  # fmt: skip


def _team_arrays(
    frame: TrackingFrame, attacking_team: str, goalkeepers: Collection[str], params: PCParams
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Positions after the reaction time (P, 2), control rates (P,), and attack mask (P,)."""
    pos = np.array([[p.x, p.y] for p in frame.players], dtype=float).reshape(-1, 2)
    vel = np.array([[p.vx, p.vy] for p in frame.players], dtype=float).reshape(-1, 2)
    attacking = np.array([p.team_id == attacking_team for p in frame.players], dtype=bool)
    is_gk = np.array([p.player_id in goalkeepers for p in frame.players], dtype=bool)
    lam = np.where(attacking, params.lambda_att, params.lambda_def)
    # Following the reference, the keeper factor applies to the defending keeper only.
    lam = np.where(is_gk & ~attacking, params.lambda_def * params.gk_factor, lam)
    reacted = pos + vel * params.reaction_time
    return reacted, lam, attacking, is_gk


def pitch_control_at(
    frame: TrackingFrame,
    attacking_team: str,
    targets: np.ndarray,
    params: PCParams | None = None,
    goalkeepers: Collection[str] = frozenset(),
    attacks_right: bool | None = None,
) -> np.ndarray:
    """Attacking team's control probability at each target (N, 2) -> (N,), in [0, 1].

    The ball starts at `frame.ball`. `goalkeepers` are player ids whose defending
    control rate is multiplied by `gk_factor` (TrackingFrame has no positions). Pass
    `attacks_right` (see `engine.pitch.attacks_right`) to drop offside attackers; `None`
    applies no offside rule.
    """
    params = params or PCParams()
    if attacks_right is not None:
        offside = offside_players(frame, attacking_team, attacks_right)
        if offside:
            keep = [p for p in frame.players if p.player_id not in offside]
            frame = frame.model_copy(update={"players": keep})
    targets = np.asarray(targets, dtype=float).reshape(-1, 2)
    n = len(targets)
    reacted, lam, attacking, _ = _team_arrays(frame, attacking_team, goalkeepers, params)
    if n == 0 or not attacking.any():
        return np.zeros(n)
    if attacking.all():
        return np.ones(n)

    ball = np.array(frame.ball[:2], dtype=float)
    ball_time = np.hypot(*(targets - ball).T) / params.average_ball_speed  # (N,)
    dist = np.hypot(
        targets[None, :, 0] - reacted[:, None, 0], targets[None, :, 1] - reacted[:, None, 1]
    )
    tti = params.reaction_time + dist / params.max_player_speed  # (P, N)
    tau_att = tti[attacking].min(axis=0)
    tau_def = tti[~attacking].min(axis=0)
    ttc_att = params.time_to_control(params.lambda_att)
    ttc_def = params.time_to_control(params.lambda_def)

    att_out = np.zeros(n)
    def_out = np.zeros(n)
    def_wins = tau_att - np.maximum(ball_time, tau_def) >= ttc_def
    att_wins = ~def_wins & (tau_def - np.maximum(ball_time, tau_att) >= ttc_att)
    att_out[att_wins] = 1.0
    def_out[def_wins] = 1.0

    todo = ~(def_wins | att_wins)
    if todo.any():
        idx = np.flatnonzero(todo)
        t_i = tti[:, idx]
        near = np.where(
            attacking[:, None],
            t_i - tau_att[idx] < ttc_att,
            t_i - tau_def[idx] < ttc_def,
        )
        rate = np.where(near, lam[:, None], 0.0)  # far players never contribute
        steepness = math.pi / math.sqrt(3.0) / params.tti_sigma
        cum = np.zeros_like(t_i)  # each player's accumulated control
        att_prev = np.zeros(len(idx))
        def_prev = np.zeros(len(idx))
        active = np.ones(len(idx), dtype=bool)
        n_steps = len(
            np.arange(-params.int_dt, params.max_int_time, params.int_dt)
        )  # matches the reference's dT_array size
        for step in range(1, n_steps):
            if not active.any():
                break
            t = ball_time[idx] + (step - 1) * params.int_dt
            p_arrive = 1.0 / (1.0 + np.exp(-steepness * (t - t_i)))
            d = (1.0 - att_prev - def_prev) * p_arrive * rate
            cum = np.where(active, cum + d * params.int_dt, cum)
            att_now = cum[attacking].sum(axis=0)
            def_now = cum[~attacking].sum(axis=0)
            att_prev = np.where(active, att_now, att_prev)
            def_prev = np.where(active, def_now, def_prev)
            active &= 1.0 - (att_prev + def_prev) > params.model_converge_tol
        att_out[idx] = att_prev
        def_out[idx] = def_prev
    return np.clip(att_out, 0.0, 1.0)


def grid_centres(nx: int = 32, ny: int = 21) -> tuple[np.ndarray, np.ndarray]:
    """Cell-centre coordinates along x (nx,) and y (ny,) on the 105 x 68 m pitch."""
    xs = (np.arange(nx) + 0.5) * PITCH_LENGTH / nx
    ys = (np.arange(ny) + 0.5) * PITCH_WIDTH / ny
    return xs, ys


def pitch_control_grid(
    frame: TrackingFrame,
    attacking_team: str,
    nx: int = 32,
    ny: int = 21,
    params: PCParams | None = None,
    goalkeepers: Collection[str] = frozenset(),
    attacks_right: bool | None = None,
) -> np.ndarray:
    """(ny, nx) surface of the attacking team's control; row 0 is y near 0."""
    xs, ys = grid_centres(nx, ny)
    gx, gy = np.meshgrid(xs, ys)
    targets = np.column_stack([gx.ravel(), gy.ravel()])
    values = pitch_control_at(frame, attacking_team, targets, params, goalkeepers, attacks_right)
    return values.reshape(ny, nx)
