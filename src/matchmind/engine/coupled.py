"""Level-3 engine: one 10 Hz loop couples players, the ball, and on-ball decisions.

Each tick: (1) `logic` resolves the ball (control, out of play, goals, saves, blocks,
tackles, decisions), (2) the ball's position is set and the frame is recorded, and
(3) every player steps toward a role target with `kinematics.step_players`. Decisions
see the pitch as it was `PERCEPTION_LAG_TICKS` ago, so a runner who releases early can
look onside to the passer and be offside when the ball is played. Kicked balls follow
`ball.flight` trajectories: whoever reaches the ball first controls it, and a ball that
crosses a line restarts by the last touch. Events stay as dicts until the period ends,
so a pass's end point and outcome are written when the ball is actually controlled.
Tunable numbers live in `engine/constants.py`.
"""

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from matchmind.engine import constants as C
from matchmind.engine.ball import (
    BALL_RADIUS_M,
    Kind,
    Trajectory,
    deflect,
    draw_speed,
    flight,
    in_goal_mouth,
    restart_for,
)
from matchmind.engine.baseline import build_frames
from matchmind.engine.decisions import (
    DecisionContext,
    Option,
    choose,
    decision_extras,
    enumerate_options,
    shot_xg,
)
from matchmind.engine.formations import formation_anchors
from matchmind.engine.kinematics import step_players
from matchmind.engine.modifiers import (
    MatchContext,
    Modifiers,
    PlayerMods,
    TeamMods,
    match_form,
)
from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH
from matchmind.engine.roles import (
    COVER_SHARE,
    GK_BASE_M,
    GK_MAX_M,
    GK_PER_M,
    PRESS_GOAL_SIDE_M,
    RUN_DEPTH_M,
    RUN_HOVER_M,
    RUN_TIMING_SD_S,
    RUN_WAIT_URGENCY,
    SUPPORT_ANGLE_DEG,
    SUPPORT_DIST_M,
    defensive_line,
    offside_line,
)
from matchmind.league.dist import stream
from matchmind.schemas import (
    Event,
    EventType,
    MatchData,
    MatchMeta,
    PlayerPos,
    TrackingFrame,
    trusted,
)
from matchmind.schemas_profile import Profiles
from matchmind.stats.pitch_control import offside_players
from matchmind.stats.xt import load_xt

ENGINE_VERSION = "l3-0.1"
CENTRE = np.array([PITCH_LENGTH / 2, PITCH_WIDTH / 2])
Chooser = Callable[[list[Option]], Option]
EventDict = dict[str, Any]
_PASS_ONLY = {"throw_in", "kickoff", "goal_kick", "corner"}
_NO_OFFSIDE = {"throw_in", "goal_kick", "corner"}


@dataclass
class _ShotPlan:
    kind: Literal["block", "save"]
    k: int  # tick of the block or save
    player: int  # blocker or keeper
    catch: bool = False


@dataclass
class _Flight:
    traj: Trajectory
    k0: int
    last_team: int
    last_player: int
    collector: int | None  # the player the ball is meant for (receiver or interceptor)
    collect_from_k: int
    free_from_k: int  # from this tick anyone may collect it
    event: EventDict | None = None  # pass/clearance/shot to resolve
    target: int | None = None  # intended receiver
    offside: bool = False
    timing_error_s: float = 0.0
    heavy_touch: bool = False
    shot: _ShotPlan | None = None
    shooter: int | None = None
    is_shot: bool = False  # the shot itself (not a deflection of it)


@dataclass
class _Dead:
    spot: np.ndarray
    taker: int
    resume_k: int
    restart: str
    kickoff: bool = False


@dataclass
class _State:
    phase: Literal["held", "flight", "dead"] = "dead"
    owner: int | None = None
    poss_team: int = 0
    decide_k: int = 0
    protect_until: int = 0
    carry_end: np.ndarray | None = None
    carry_event: EventDict | None = None
    flight: _Flight | None = None
    dead: _Dead | None = None
    restart: str | None = None
    reset_shape: bool = False
    runner: int | None = None
    run_start_k: int | None = None
    run_end_k: int = 0
    run_error_s: float = 0.0
    transition_until: int = 0


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.hypot(v[0], v[1]))
    return v / n if n > 1e-9 else np.zeros(2)


def _clamp(p: np.ndarray, margin: float = 0.0) -> np.ndarray:
    return np.array([min(max(float(p[0]), margin), PITCH_LENGTH - margin),
                     min(max(float(p[1]), margin), PITCH_WIDTH - margin)])  # fmt: skip


class Coupled:
    def __init__(
        self,
        meta: MatchMeta,
        tracking: bool = True,
        player_mods: list[PlayerMods] | None = None,
        team_mods: tuple[TeamMods, TeamMods] | None = None,
        xt: np.ndarray | None = None,
    ) -> None:
        self.meta = meta
        self.tracking = tracking
        self.rng = stream(meta.seed, "engine-l3")
        self.players = meta.home_squad[:11] + meta.away_squad[:11]
        self.ids = [p.player_id for p in self.players]
        self.team_ids = (meta.home.club_id, meta.away.club_id)
        self.team_of = np.array([0] * 11 + [1] * 11)
        self.anchors = np.vstack(
            [formation_anchors(meta.home.formation), formation_anchors(meta.away.formation)]
        )
        self.is_df = np.array([p.position == "DF" for p in self.players])
        self.is_fw = np.array([p.position == "FW" for p in self.players])
        self.skill = np.array([p.skill for p in self.players])
        self.pace = np.array([p.pace for p in self.players])
        self.stamina = np.array([p.stamina for p in self.players])
        self.goalkeepers = frozenset({self.ids[0], self.ids[11]})
        self.pmods = player_mods or [PlayerMods() for _ in range(22)]
        self.tmods = team_mods or (TeamMods(), TeamMods())
        self.drain = np.array([m.energy_drain for m in self.pmods])
        self.xt = load_xt() if xt is None else xt
        self.energy = np.array([min(1.0, m.start_energy) for m in self.pmods])
        self.chooser: Chooser | None = None
        self.events: list[EventDict] = []  # this period, resolved at its end
        self.all_events: list[Event] = []
        self.frames: list[TrackingFrame] = []
        self.rec_pos: list[np.ndarray] = []
        self.rec_vel: list[np.ndarray] = []
        self.rec_ball: list[tuple[float, float, float]] = []
        self.history: deque[tuple[np.ndarray, np.ndarray]] = deque(
            maxlen=C.PERCEPTION_LAG_TICKS + 1
        )
        self.period: Literal[1, 2] = 1
        self.k = 0
        self.n_ticks = 0
        self.seq = 0
        self.pos = np.zeros((22, 2))
        self.spot = np.zeros((22, 2))  # settled shape targets (see SHAPE_DEADBAND_M)
        self.vel = np.zeros((22, 2))
        self.ball = CENTRE.copy()
        self.ball_z = BALL_RADIUS_M
        self.s = _State()

    # ---- geometry -----------------------------------------------------------------------

    def right(self, team: int) -> bool:
        return (team == 0) == (self.period == 1)

    def local(self, xy: np.ndarray, team: int) -> np.ndarray:
        """Absolute <-> team frame (the map is its own inverse)."""
        if self.right(team):
            return np.array(xy, dtype=float)
        out: np.ndarray = np.array([PITCH_LENGTH, PITCH_WIDTH]) - xy
        return out

    def members(self, team: int) -> range:
        return range(11 * team, 11 * team + 11)

    def dist(self, i: int, point: np.ndarray) -> float:
        return float(math.hypot(self.pos[i, 0] - point[0], self.pos[i, 1] - point[1]))

    def in_own_box(self, gk: int, point: np.ndarray) -> bool:
        local = self.local(np.array(point[:2]), int(self.team_of[gk]))
        return bool(local[0] <= C.BOX_DEPTH_M and abs(local[1] - CENTRE[1]) <= C.BOX_HALF_WIDTH_M)

    def near_own_goal(self, j: int, point: np.ndarray) -> bool:
        return bool(self.local(np.array(point[:2]), int(self.team_of[j]))[0] <= C.DEFLECT_DEPTH_M)

    def nearest(self, point: np.ndarray, team: int, outfield: bool = True) -> int:
        lo = 11 * team + (1 if outfield else 0)
        d = np.hypot(*(self.pos[lo : 11 * team + 11] - point[:2]).T)
        return lo + int(np.argmin(d))

    def frame(self, lagged: bool = False) -> TrackingFrame:
        pos, vel = self.history[0] if lagged and self.history else (self.pos, self.vel)
        players = [
            trusted(PlayerPos, {"player_id": self.ids[i], "team_id": self.team_ids[i // 11],
                                "x": float(pos[i, 0]), "y": float(pos[i, 1]),
                                "vx": float(vel[i, 0]), "vy": float(vel[i, 1])})
            for i in range(22)
        ]  # fmt: skip
        return trusted(TrackingFrame, {"match_id": self.meta.match_id, "frame": 0,
                                       "period": self.period, "t": self.k * C.DT,
                                       "ball": (float(self.ball[0]), float(self.ball[1]),
                                                float(self.ball_z)),
                                       "players": players})  # fmt: skip

    # ---- events -------------------------------------------------------------------------

    def emit(
        self,
        type_: EventType,
        team: int,
        player: int | None,
        at: np.ndarray,
        *,
        end: np.ndarray | None = None,
        outcome: bool | None = None,
        receiver: int | None = None,
        speed: float | None = None,
        extras: dict[str, object] | None = None,
    ) -> EventDict:
        ev: EventDict = {
            "t": round(self.k * C.DT, 1),
            "seq": self.seq,
            "type": type_,
            "team": team,
            "player_id": None if player is None else self.ids[player],
            "at": np.array(at[:2], dtype=float),
            "end": end,
            "outcome": outcome,
            "receiver": receiver,
            "speed": speed,
            "extras": dict(extras or {}),
        }
        self.seq += 1
        self.events.append(ev)
        return ev

    def resolve(self, ev: EventDict | None, end: np.ndarray, outcome: bool,
                receiver: int | None = None) -> None:  # fmt: skip
        if ev is None or ev["outcome"] is not None:
            return
        ev["end"] = np.array(end[:2], dtype=float)
        ev["outcome"] = outcome
        ev["receiver"] = receiver
        if ev["type"] in ("pass", "kickoff", "clearance"):
            ev["extras"]["arrival_t"] = round(self.k * C.DT, 1)

    def _to_event(self, ev: EventDict, n: int) -> Event:
        end = ev["end"]
        receiver = ev["receiver"]
        return Event(
            event_id=f"{self.meta.match_id}-e{n:05d}",
            match_id=self.meta.match_id,
            period=self.period,
            t=ev["t"],
            type=ev["type"],
            team_id=self.team_ids[ev["team"]],
            player_id=ev["player_id"],
            x=round(float(ev["at"][0]), 2),
            y=round(float(ev["at"][1]), 2),
            end_x=None if end is None else round(float(end[0]), 2),
            end_y=None if end is None else round(float(end[1]), 2),
            outcome=ev["outcome"],
            receiver_id=None if receiver is None else self.ids[receiver],
            ball_speed_ms=ev["speed"],
            extras=ev["extras"],
        )

    # ---- possession, restarts -----------------------------------------------------------

    def kickoff_shape(self) -> np.ndarray:
        out = np.zeros((22, 2))
        for team in (0, 1):
            idx = list(self.members(team))
            a = self.anchors[idx].copy()
            a[:, 0] = np.minimum(a[:, 0] - 6.0, PITCH_LENGTH / 2 - 1.5)
            a[:, 1] = PITCH_WIDTH / 2 + (a[:, 1] - PITCH_WIDTH / 2) * C.DEFEND_WIDTH
            out[idx] = self.local(a, team)
        return out

    def give_ball(
        self, i: int, hold_s: float | None = None, protect_s: float = C.PROTECT_S
    ) -> None:
        s = self.s
        if hold_s is None:
            hold_s = float(self.rng.uniform(*C.DECIDE_DELAY_S))
        if s.poss_team != int(self.team_of[i]):
            s.runner = None
            s.transition_until = self.k + round(C.TRANSITION_S / C.DT)
        s.phase, s.owner, s.poss_team = "held", i, int(self.team_of[i])
        s.decide_k = self.k + max(1, round(hold_s / C.DT))
        s.protect_until = self.k + round(protect_s / C.DT)
        s.flight, s.dead, s.carry_end = None, None, None
        self.schedule_run()

    def pick_runner(self, team: int) -> int | None:
        fws = [j for j in self.members(team) if self.is_fw[j] and j != self.s.owner]
        if not fws:
            return None
        depth = [float(self.local(self.pos[j], team)[0]) for j in fws]
        return fws[int(np.argmax(depth))]

    def schedule_run(self) -> None:
        """The runner releases at the next decision minus a timing error (early > 0)."""
        s = self.s
        assert s.owner is not None
        team = int(self.team_of[s.owner])
        if s.runner is None or s.runner == s.owner:
            s.runner = self.pick_runner(team)
        if s.runner is None:
            return
        sd = RUN_TIMING_SD_S * self.pmods[s.runner].run_timing_sd
        self.set_run(s.runner, float(self.rng.normal(0.0, sd)))

    def set_run(self, runner: int, error_s: float) -> None:
        s = self.s
        s.runner, s.run_error_s = runner, error_s
        s.run_start_k = s.decide_k - round(error_s / C.DT)
        s.run_end_k = s.decide_k + round(C.RUN_MAX_S / C.DT)

    def force_run(self, runner: int, timing_error_s: float) -> None:
        """Fixtures: make `runner` release `timing_error_s` before the next decision."""
        self.set_run(runner, timing_error_s)

    def start_dead(self, spot: np.ndarray, taker: int, restart: str, pause_s: float | None = None,
                   kickoff: bool = False) -> None:  # fmt: skip
        s = self.s
        if pause_s is None:
            pause_s = float(self.rng.uniform(*C.PAUSE_S[restart]))
        self.end_carry(False)
        s.phase, s.owner, s.flight = "dead", None, None
        s.poss_team = int(self.team_of[taker])
        s.dead = _Dead(np.array(spot, dtype=float), taker, self.k + round(pause_s / C.DT),
                       restart, kickoff)  # fmt: skip
        s.runner = None
        self.ball, self.ball_z = s.dead.spot.copy(), BALL_RADIUS_M

    def resume(self) -> None:
        s = self.s
        dead = s.dead
        assert dead is not None
        s.reset_shape = False
        s.restart = dead.restart
        self.give_ball(dead.taker, hold_s=C.RESTART_DECIDE_S, protect_s=2.0)
        if dead.kickoff:
            team = int(self.team_of[dead.taker])
            mids = [j for j in self.members(team) if j != dead.taker and not self.is_df[j]
                    and not self.is_fw[j] and j % 11 != 0]  # fmt: skip
            j = mids[int(self.rng.integers(len(mids)))]
            opt = Option("pass", self.ids[j], (float(self.pos[j, 0]), float(self.pos[j, 1])),
                         0.0)  # fmt: skip
            s.restart = None
            self.kick(dead.taker, opt, {}, type_="kickoff", sure=True)

    def ball_out(self, point: np.ndarray, f: _Flight) -> None:
        self.resolve(f.event, point, False)
        if in_goal_mouth(point):
            self.goal(point, f)
            return
        restart = restart_for(point, self.right(f.last_team))
        self.emit("out", f.last_team, f.last_player, point, extras={"restart": restart})
        if restart == "throw_in":
            spot = np.array(point[:2], dtype=float)
            self.start_dead(spot, self.nearest(spot, 1 - f.last_team), restart)
            return
        # The team whose goal is on this line defends it.
        defending = 0 if (point[0] < PITCH_LENGTH / 2) == self.right(0) else 1
        if restart == "corner":
            spot = np.array([0.0 if point[0] < PITCH_LENGTH / 2 else PITCH_LENGTH,
                             0.0 if point[1] < PITCH_WIDTH / 2 else PITCH_WIDTH])  # fmt: skip
            self.start_dead(spot, self.nearest(spot, 1 - defending), restart)
        else:
            w = PITCH_WIDTH / 2 + float(self.rng.uniform(-9.0, 9.0))
            spot = self.local(np.array([5.5, w]), defending)
            self.start_dead(spot, 11 * defending, restart)

    def scores_for(self, point: np.ndarray) -> int:
        """The team that scores when the ball crosses the goal line at `point`."""
        return 0 if (point[0] >= PITCH_LENGTH / 2) == self.right(0) else 1

    def goal(self, point: np.ndarray, f: _Flight) -> None:
        scoring = self.scores_for(point)
        if f.shooter is not None and int(self.team_of[f.shooter]) == scoring:
            scorer: int | None = f.shooter
        else:
            scorer = f.last_player if f.last_team == scoring else None
        own_goal = scorer is None
        extras: dict[str, object] = {"own_goal": True} if own_goal else {}
        self.emit("goal", scoring, scorer, point, outcome=True, extras=extras)
        pause = min(C.GOAL_PAUSE_S, (self.n_ticks - self.k) * C.DT - 3.0)
        self.s.reset_shape = True
        conceding = 1 - scoring
        taker = max(self.members(conceding), key=lambda j: float(self.anchors[j, 0]))
        self.start_dead(CENTRE.copy(), taker, "kickoff", pause_s=max(pause, 1.0), kickoff=True)

    # ---- on-ball actions ----------------------------------------------------------------

    def decide(self, i: int) -> None:
        s = self.s
        team = int(self.team_of[i])
        self.end_carry(True)
        ctx = DecisionContext(self.team_ids[team], self.right(team), self.xt, self.goalkeepers,
                              risk_weight=self.pmods[i].risk_weight, shot_cost=C.SHOT_COST,
                              clear_bonus=C.CLEAR_BONUS)  # fmt: skip
        options = enumerate_options(self.frame(lagged=True), self.ids[i], ctx)
        restart = s.restart
        if restart in _PASS_ONLY or i % 11 == 0:
            options = [o for o in options if o.kind in ("pass", "through", "clear")]
        if restart == "throw_in":
            options = [o for o in options if math.dist(o.end, self.ball[:2]) <= C.THROW_MAX_M]
        if not options:
            s.decide_k = self.k + 3
            return
        if self.chooser is not None:
            opt = self.chooser(options)
        else:
            opt = choose(
                options, float(self.skill[i]), self.rng, self.pmods[i].decision_temperature
            )
        extras = decision_extras(opt, options)
        if restart:
            extras["restart"] = restart
            s.restart = None
        if opt.kind in ("pass", "through"):
            self.kick(i, opt, extras, restart=restart)
        elif opt.kind == "carry":
            self.start_carry(i, opt, extras)
        elif opt.kind == "shot":
            self.shoot(i, extras)
        else:
            self.clear(i, opt, extras)

    def end_carry(self, completed: bool) -> None:
        s = self.s
        if s.carry_event is not None and s.owner is not None:
            self.resolve(s.carry_event, self.pos[s.owner], completed)
        s.carry_event, s.carry_end = None, None

    def start_carry(self, i: int, opt: Option, extras: dict[str, object]) -> None:
        s = self.s
        s.carry_end = np.array(opt.end)
        s.carry_event = self.emit("carry", int(self.team_of[i]), i, self.ball, extras=extras)
        dur = math.dist(opt.end, self.pos[i]) / (0.6 * C.DRIBBLE_MAX_MS)
        s.decide_k = self.k + max(2, round(dur / C.DT))
        self.schedule_run()

    def launch(self, f: _Flight) -> None:
        s = self.s
        s.phase, s.owner, s.flight, s.carry_end = "flight", None, f, None
        s.run_start_k = None

    def interceptor(self, traj: Trajectory, team: int) -> tuple[int, int] | None:
        """The opponent who can reach the ball's path first, and the tick from which he may
        take it."""
        pts = traj.xyz
        ok = ((pts[:, 2] <= C.CONTROL_HEIGHT_M) & (pts[:, 0] >= 0) & (pts[:, 0] <= PITCH_LENGTH)
              & (pts[:, 1] >= 0) & (pts[:, 1] <= PITCH_WIDTH))  # fmt: skip
        ok[:3] = False
        if not ok.any():
            return None
        opp = np.array(self.members(1 - team))
        d = np.hypot(
            self.pos[opp, None, 0] - pts[None, :, 0], self.pos[opp, None, 1] - pts[None, :, 1]
        )
        reach = C.INTERCEPT_REACT_S + d / C.INTERCEPT_SPEED_MS
        can = (reach <= traj.t[None, :]) & ok[None, :]
        cols = np.flatnonzero(can.any(axis=0))
        if len(cols) == 0:
            return None
        j = int(cols[0])
        o = int(opp[np.argmin(np.where(can[:, j], reach[:, j], np.inf))])
        return o, self.k + max(1, j - 2)

    def kick(self, i: int, opt: Option, extras: dict[str, object], *, type_: EventType = "pass",
             restart: str | None = None, sure: bool = False) -> None:  # fmt: skip
        team = int(self.team_of[i])
        skill = float(self.skill[i])
        start = self.ball.copy()
        target = self.ids.index(opt.target_player_id) if opt.target_player_id else None
        end = np.array(opt.end)
        d = max(float(np.hypot(*(end - start))), 1.0)
        kind: Kind = "lofted" if d >= C.LOFT_MIN_M or restart == "corner" else "ground"
        err = C.PASS_ERR_DEG * (1.5 - skill) * self.pmods[i].pass_error
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        angle += math.radians(float(self.rng.normal(0.0, err))) if not sure else 0.0
        length = (
            d * (1.0 + float(self.rng.normal(0.0, C.LOFT_LENGTH_ERR))) if kind == "lofted" else d
        )
        aim = start + length * np.array([math.cos(angle), math.sin(angle)])
        speed = C.THROW_SPEED_MS if restart == "throw_in" else draw_speed(self.rng, kind, d, skill)
        traj = flight(start, aim, kind, speed)
        for _ in range(3):
            if traj.reaches_end or kind != "ground" or traj.out_of_play() is not None:
                break
            speed = min(speed + 2.0, 22.0)
            traj = flight(start, aim, kind, speed)
        for _ in range(6):
            # Nobody passes into his own net: a ball that would roll in is played softer.
            out = traj.out_of_play()
            if out is None or not in_goal_mouth(out[1]) or self.scores_for(out[1]) == team:
                break
            speed *= 0.75
            traj = flight(start, aim, kind, speed)
        offside = (target is not None and restart not in _NO_OFFSIDE
                   and self.ids[target] in offside_players(self.frame(), self.team_ids[team],
                                                           self.right(team)))  # fmt: skip
        p_ok = 1.0 if sure else opt.pc_prob**C.PC_EXP * (C.EXEC_BASE + C.EXEC_SKILL * skill)
        collector, heavy = target, False
        collect_from = self.k + 2
        if self.rng.random() >= p_ok:
            cut = self.interceptor(traj, team)
            if cut is not None:
                collector, collect_from = cut
            else:
                heavy = target is not None
        timing = self.s.run_error_s if target is not None and target == self.s.runner else 0.0
        ev = self.emit(type_, team, i, start, speed=round(speed, 2), extras=extras)
        free = self.k + round((traj.duration + C.FREE_AFTER_S) / C.DT)
        self.launch(_Flight(traj, self.k, team, i, collector, collect_from, free, ev, target,
                            offside, round(timing, 2), heavy))  # fmt: skip

    def clear(self, i: int, opt: Option, extras: dict[str, object]) -> None:
        team = int(self.team_of[i])
        start = self.ball.copy()
        end = np.array(opt.end)
        d = float(np.hypot(*(end - start)))
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        angle += math.radians(float(self.rng.normal(0.0, C.CLEAR_ERR_DEG)))
        aim = start + d * np.array([math.cos(angle), math.sin(angle)])
        speed = draw_speed(self.rng, "lofted", d, float(self.skill[i]))
        traj = flight(start, aim, "lofted", speed)
        ev = self.emit("clearance", team, i, start, speed=round(speed, 2), extras=extras)
        free = self.k + max(3, round(traj.duration / C.DT))
        self.launch(_Flight(traj, self.k, team, i, None, free, free, ev))

    def shoot(self, i: int, extras: dict[str, object]) -> None:
        team = int(self.team_of[i])
        skill = float(self.skill[i])
        start = self.ball.copy()
        xg = shot_xg(start, self.right(team), skill)
        aim_local = np.array([PITCH_LENGTH, PITCH_WIDTH / 2 + float(self.rng.uniform(
            -(3.66 - C.SHOT_AIM_INSIDE_M), 3.66 - C.SHOT_AIM_INSIDE_M))])  # fmt: skip
        aim = self.local(aim_local, team)
        err = C.SHOT_ERR_DEG * (1.5 - skill) * self.pmods[i].shot_error
        angle = math.atan2(aim[1] - start[1], aim[0] - start[0])
        angle += math.radians(float(self.rng.normal(0.0, err)))
        d = float(np.hypot(*(aim - start)))
        target = start + (d + 3.0) * np.array([math.cos(angle), math.sin(angle)])
        speed = draw_speed(self.rng, "shot", d, skill)
        traj = flight(
            start, target, "shot", speed, loft_deg=float(self.rng.uniform(*C.SHOT_LOFT_DEG))
        )
        extras = {**extras, "xg": round(xg, 3)}
        ev = self.emit("shot", team, i, start, speed=round(speed, 2), extras=extras)
        never = self.k + len(traj.t) + 1
        f = _Flight(traj, self.k, team, i, None, never, never, ev, shooter=i, is_shot=True)
        f.shot = self.plan_shot(traj, team, xg)
        self.launch(f)

    def plan_shot(self, traj: Trajectory, team: int, xg: float) -> _ShotPlan | None:
        """A defender on the shot's line may block it; a shot on target may be saved."""
        start = traj.xyz[0, :2]
        stop = traj.out[1][:2] if traj.out is not None else traj.xyz[-1, :2]
        seg = stop - start
        length = float(np.hypot(*seg))
        if length < 1e-6:
            return None
        u_hat = seg / length
        blockers = []
        for o in self.members(1 - team):
            if o % 11 == 0:
                continue
            rel = self.pos[o] - start
            u = float(rel @ u_hat)
            perp = abs(float(rel[0] * u_hat[1] - rel[1] * u_hat[0]))
            if 0.5 < u < length - 1.0 and perp < C.BLOCK_REACH_M:
                blockers.append((u, o))
        along = np.hypot(*(traj.xyz[:, :2] - start).T)
        for u, o in sorted(blockers):
            if self.rng.random() < C.BLOCK_PROB:
                idx = int(np.searchsorted(along, u))
                return _ShotPlan("block", self.k + max(1, idx), o)
        if traj.out is None or not in_goal_mouth(traj.out[1]):
            return None
        gk = 11 * (1 - team)
        p_save = C.SAVE_BASE - C.SAVE_XG * xg + C.SAVE_SKILL * (float(self.skill[gk]) - 0.5)
        p_save = min(max(p_save / self.pmods[gk].gk_error, 0.05), 0.95)
        if self.rng.random() >= p_save:
            return None
        speed = float(np.hypot(*(traj.xyz[1, :2] - traj.xyz[0, :2]))) / C.DT
        catch = self.rng.random() < C.CATCH_PROB[0 if speed < C.CATCH_SPEED_MS else 1]
        k_save = self.k + max(1, math.floor((traj.out[0] - C.SAVE_LEAD_S) / C.DT))
        return _ShotPlan("save", k_save, gk, catch)

    def deflected(self, f: _Flight, at: np.ndarray, player: int, kind: Literal["block", "parry"],
                  safe: bool = False) -> None:  # fmt: skip
        """The ball comes off `player`. `safe` (a defender's touch in his own box) aims it
        partly toward his own goal line, so it often goes behind for a corner."""
        team = int(self.team_of[player])
        t = (self.k - f.k0) * C.DT
        before = f.traj.positions_at(max(t - C.DT, 0.0))[:2]
        incoming = at[:2] - before
        speed = float(np.hypot(*incoming)) / C.DT
        if safe:
            line = np.array([-1.0 if self.right(team) else 1.0, 0.0])
            w = C.SAFE_TOUCH_LINE_WEIGHT
            incoming = ((1 - w) * _unit(incoming) + w * line) * max(speed, 1e-6)
        direction, new_speed = deflect(self.rng, (float(incoming[0]), float(incoming[1])),
                                       max(speed, 5.0), kind)  # fmt: skip
        if safe:
            new_speed = float(self.rng.uniform(*C.SAFE_TOUCH_SPEED_MS))
        start = _clamp(at[:2], 0.05)
        traj = flight(start, start + 40.0 * direction, "ground", new_speed)
        out = traj.out_of_play()
        if (kind == "parry" or safe) and out is not None and in_goal_mouth(out[1]):
            # Keepers and defenders push the ball away from their goal, never into it.
            u = _unit(incoming)
            direction = direction - 2.0 * float(direction @ u) * u
            traj = flight(start, start + 40.0 * direction, "ground", new_speed)
        self.launch(_Flight(traj, self.k, team, player, None, self.k + 2, self.k + 2,
                            shooter=f.shooter))  # fmt: skip

    def resolve_shot(self, f: _Flight, at: np.ndarray) -> None:
        plan = f.shot
        assert plan is not None
        self.resolve(f.event, at, False)
        if plan.kind == "block":
            if f.event is not None:
                f.event["extras"]["blocked"] = True
            self.deflected(f, at, plan.player, "block")
            return
        gk = plan.player
        team = int(self.team_of[gk])
        self.emit("save", team, gk, at, outcome=True,
                  extras={} if plan.catch else {"parried": True})  # fmt: skip
        if plan.catch:
            self.give_ball(gk, hold_s=float(self.rng.uniform(2.0, 5.0)), protect_s=3.0)
        else:
            self.deflected(f, at, gk, "parry")

    def try_tackle(self, i: int) -> None:
        s = self.s
        team = int(self.team_of[i])
        o = self.nearest(self.pos[i], 1 - team)
        if self.dist(o, self.pos[i]) > C.TACKLE_RANGE_M:
            return
        if self.rng.random() > C.TACKLE_RATE_PER_TICK * self.pmods[o].tackle_rate:
            return
        at = self.ball.copy()
        if self.rng.random() < C.FOUL_SHARE * self.pmods[o].foul_rate:
            mods = self.pmods[o].to_extras(("foul_rate", "tackle_rate"))
            self.emit("foul", 1 - team, o, at, extras={"mods": mods})
            self.start_dead(_clamp(at, 0.5), i, "free_kick")
            return
        won = self.rng.random() < C.TACKLE_WIN + 0.3 * float(self.skill[o] - self.skill[i])
        self.emit("tackle", 1 - team, o, at, outcome=won)
        if not won:
            s.protect_until = self.k + round(C.PROTECT_S / C.DT)
            return
        self.end_carry(False)
        if self.near_own_goal(o, at) and self.rng.random() < C.BOX_DEFLECT_SHARE:
            f = _Flight(flight(at, at, "ground", 1.0), self.k, team, i, None, self.k, self.k)
            self.deflected(f, at, o, "block", safe=True)
            return
        if self.rng.random() < C.TACKLE_LOOSE_SHARE:
            a = float(self.rng.uniform(0, 2 * math.pi))
            start = _clamp(at, 0.05)
            traj = flight(start, start + 10.0 * np.array([math.cos(a), math.sin(a)]), "ground",
                          float(self.rng.uniform(3.0, 7.0)))  # fmt: skip
            self.launch(_Flight(traj, self.k, 1 - team, o, None, self.k + 2, self.k + 2))
        else:
            self.give_ball(o)

    def control(self, j: int, f: _Flight, at: np.ndarray) -> None:
        s = self.s
        team = int(self.team_of[j])
        if f.heavy_touch and j == f.collector:
            self.resolve(f.event, at, False)
            if f.event is not None:
                f.event["extras"]["heavy_touch"] = True
            a = float(self.rng.uniform(0, 2 * math.pi))
            start = _clamp(at, 0.05)
            traj = flight(start, start + 10.0 * np.array([math.cos(a), math.sin(a)]), "ground",
                          float(self.rng.uniform(*C.HEAVY_TOUCH_SPEED)))  # fmt: skip
            self.launch(_Flight(traj, self.k, team, j, None, self.k + 3, self.k + 3))
            return
        if team == f.last_team and f.offside and j == f.target:
            self.resolve(f.event, at, False, j)
            if f.event is not None:
                f.event["extras"]["offside"] = True
            mods = self.pmods[j].to_extras(("run_timing_sd",))
            self.emit("offside", team, j, at,
                      extras={"timing_error_s": f.timing_error_s, "mods": mods})  # fmt: skip
            spot = _clamp(at, 0.5)
            self.start_dead(spot, self.nearest(spot, 1 - team), "free_kick")
            return
        feet = self.at_feet(j)  # where the ball sits once controlled
        self.resolve(f.event, feet, team == f.last_team, j if team == f.last_team else None)
        if (team != f.last_team and j % 11 != 0 and self.near_own_goal(j, at)
                and self.rng.random() < C.BOX_DEFLECT_SHARE):  # fmt: skip
            # Under pressure near his own goal a defender heads or hooks the ball away.
            self.emit("clearance", team, j, at, extras={"deflection": True})
            self.deflected(f, at, j, "block", safe=True)
            return
        if team != f.last_team:
            self.emit("interception", team, j, feet, outcome=True)
        s.flight = None
        self.give_ball(j)

    def flight_logic(self) -> None:
        f = self.s.flight
        assert f is not None
        t = (self.k - f.k0) * C.DT
        b = f.traj.positions_at(t)
        if f.shot is not None and self.k >= f.shot.k:
            self.resolve_shot(f, b)
            return
        out = f.traj.out
        if out is not None and t >= out[0]:
            self.ball_out(out[1], f)
            return
        if b[2] > C.CONTROL_HEIGHT_M:
            return
        # The ball travels up to 2-3 m per tick: reach is measured to its path since the
        # last tick, and it is controlled at the nearest point of that path.
        prev = f.traj.positions_at(max(t - C.DT, 0.0))[:2]
        near, d = self._reach(prev, b[:2])
        if f.collector is not None and self.k >= f.collect_from_k:
            j = f.collector
            if d[j] <= C.CONTROL_RANGE_M:
                self.control(j, f, near[j])
                return
        if self.k >= f.free_from_k:
            j = int(np.argmin(d))
            if d[j] <= C.CONTROL_RANGE_M:
                self.control(j, f, near[j])
                return
        # Keepers use their hands in their own box: a wider reach for any ball but a shot.
        if not f.is_shot:
            for gk in (0, 11):
                if (gk != f.last_player and self.in_own_box(gk, near[gk])
                        and d[gk] <= C.GK_CONTROL_RANGE_M):  # fmt: skip
                    self.control(gk, f, near[gk])
                    return

    def _reach(self, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Each player's nearest point on the segment a-b, and the distance to it."""
        seg = b - a
        n2 = float(seg @ seg)
        u = np.clip((self.pos - a) @ seg / n2, 0.0, 1.0) if n2 > 1e-12 else np.zeros(22)
        near = a + u[:, None] * seg
        return near, np.hypot(*(self.pos - near).T)

    def logic(self) -> None:
        s = self.s
        if s.phase == "dead":
            assert s.dead is not None
            if self.k >= s.dead.resume_k and self.dist(s.dead.taker, s.dead.spot) <= 1.0:
                self.resume()
        elif s.phase == "flight":
            self.flight_logic()
        if s.phase == "held":
            assert s.owner is not None
            i = s.owner
            if self.k >= s.protect_until:
                self.try_tackle(i)
            if s.phase == "held" and s.owner == i and self.k >= s.decide_k:
                self.decide(i)

    # ---- movement -----------------------------------------------------------------------

    def shape(self) -> tuple[np.ndarray, np.ndarray]:
        """Formation targets for everyone, shifted with the ball; then urgency by distance."""
        s = self.s
        if s.reset_shape:
            tgt = self.kickoff_shape()
        else:
            tgt = np.zeros((22, 2))
            for team in (0, 1):
                idx = slice(11 * team, 11 * team + 11)
                b = self.local(self.ball, team)
                a = self.anchors[idx]
                shift = C.BLOCK_SHIFT * (b[0] - CENTRE[0])
                side = C.BALL_SIDE_SHIFT * (b[1] - CENTRE[1])
                if s.poss_team == team:
                    d = a[:, 0] + shift + C.ATTACK_PUSH_M
                    w = CENTRE[1] + (a[:, 1] - CENTRE[1]) * C.ATTACK_WIDTH + side
                    d[0] = min(C.GK_DEPTH_IN_POSSESSION, max(b[0] - 20.0, 4.0))
                    w[0] = CENTRE[1]
                else:
                    d = a[:, 0] + shift - C.DEFEND_DROP_M
                    w = CENTRE[1] + (a[:, 1] - CENTRE[1]) * C.DEFEND_WIDTH + side
                    df = self.is_df[idx]
                    if df.any():
                        d[df] = defensive_line(a[df, 0], float(b[0]),
                                               self.tmods[team].line_height)  # fmt: skip
                    to_ball = b - np.array([0.0, CENTRE[1]])
                    gd = min(max(GK_BASE_M + GK_PER_M * float(np.hypot(*to_ball)), GK_BASE_M),
                             GK_MAX_M)  # fmt: skip
                    g = np.array([0.0, CENTRE[1]]) + gd * _unit(to_ball)
                    d[0], w[0] = g[0], g[1]
                local = np.column_stack([np.clip(d, 0.5, PITCH_LENGTH - 0.5),
                                         np.clip(w, 0.5, PITCH_WIDTH - 0.5)])  # fmt: skip
                tgt[idx] = self.local(local, team)
        moved = np.hypot(*(tgt - self.spot).T) > C.SHAPE_DEADBAND_M
        self.spot[moved] = tgt[moved]
        tgt = self.spot.copy()
        dist = np.hypot(*(tgt - self.pos).T)
        urg = np.clip(dist * C.SHAPE_URGENCY_PER_M, *C.SHAPE_URGENCY)
        if self.k < s.transition_until:
            urg[dist > C.TRANSITION_MIN_M] = C.TRANSITION_URGENCY
        return tgt, urg

    def defend_ball(self, tgt: np.ndarray, urg: np.ndarray, team: int) -> None:
        """Out of possession: the nearest player presses (or contains), the next covers."""
        lo = 11 * team + 1
        d = np.hypot(*(self.pos[lo : lo + 10] - self.ball).T)
        order = lo + np.argsort(d)
        b = self.local(self.ball, team)
        own_goal = np.array([0.0, CENTRE[1]])
        intensity = self.tmods[team].press_intensity
        presser, cover = int(order[0]), int(order[1])
        if b[0] <= C.PRESS_BASE_M + intensity * C.PRESS_ZONE_M:
            p = b + PRESS_GOAL_SIDE_M * _unit(own_goal - b)
            u = C.PRESS_URGENCY[0] + intensity * (C.PRESS_URGENCY[1] - C.PRESS_URGENCY[0])
            urg[presser] = min(1.0, u * self.pmods[presser].press_urgency)
        else:
            p = b + C.CONTAIN_M * _unit(own_goal - b)
            urg[presser] = C.SUPPORT_URGENCY
        tgt[presser] = self.local(_clamp(p, 0.5), team)
        c = 0.5 * (b + COVER_SHARE * (own_goal - b)) + 0.5 * self.local(tgt[cover], team)
        tgt[cover] = self.local(_clamp(c, 0.5), team)

    def attack_ball(self, tgt: np.ndarray, urg: np.ndarray, team: int, carrier: int) -> None:
        """In possession: the two nearest teammates offer angles; the runner times a run."""
        s = self.s
        b = self.local(self.ball, team)
        runner = s.runner
        lo = 11 * team + 1
        cands = [j for j in range(lo, lo + 10) if j not in (carrier, runner)]
        d = [self.dist(j, self.ball) for j in cands]
        for rank, j in enumerate(np.array(cands)[np.argsort(d)[:2]]):
            side = -1.0 if rank == 0 else 1.0
            ang = math.radians(SUPPORT_ANGLE_DEG)
            p = b + SUPPORT_DIST_M * np.array([math.cos(ang), side * math.sin(ang)])
            tgt[j] = self.local(_clamp(p, 1.0), team)
            urg[j] = C.SUPPORT_URGENCY
        if runner is None or b[0] < C.RUN_BALL_DEPTH_M:
            return
        opp = self.pos[list(self.members(1 - team))]
        line = offside_line(opp, self.ball, self.right(team))
        line_local = float(self.local(np.array([line, 0.0]), team)[0])
        here = self.local(self.pos[runner], team)
        running = s.run_start_k is not None and s.run_start_k <= self.k < s.run_end_k
        depth = line_local + RUN_DEPTH_M if running else line_local - RUN_HOVER_M
        tgt[runner] = self.local(_clamp(np.array([depth, here[1]]), 0.5), team)
        urg[runner] = 1.0 if running else RUN_WAIT_URGENCY

    def targets(self) -> tuple[np.ndarray, np.ndarray]:
        s = self.s
        tgt, urg = self.shape()
        if s.phase == "held" and s.owner is not None:
            i = s.owner
            team = int(self.team_of[i])
            self.attack_ball(tgt, urg, team, i)
            self.defend_ball(tgt, urg, 1 - team)
            if s.carry_end is not None:
                tgt[i], urg[i] = s.carry_end, C.DRIBBLE_URGENCY
            else:
                tgt[i], urg[i] = self.pos[i], C.HOLD_URGENCY
        elif s.phase == "flight" and s.flight is not None:
            f = s.flight
            t = (self.k - f.k0) * C.DT
            arrival = f.traj.positions_at(max(f.traj.duration, t))[:2]
            if f.shot is not None and f.shot.kind == "save":
                gk = f.shot.player
                tgt[gk] = f.traj.positions_at((f.shot.k - f.k0) * C.DT)[:2]
                urg[gk] = C.CHASE_URGENCY
            if f.collector is not None:
                if int(self.team_of[f.collector]) == f.last_team:
                    point = arrival
                else:
                    point = f.traj.positions_at(max((f.collect_from_k - f.k0 + 2) * C.DT, t))[:2]
                tgt[f.collector], urg[f.collector] = point, C.CHASE_URGENCY
            if f.target is not None and f.target != f.collector:
                tgt[f.target], urg[f.target] = arrival, C.CHASE_URGENCY
            if self.k >= f.free_from_k - 10 or f.collector is None:
                ahead = f.traj.positions_at(t + 0.5)[:2]
                for team in (0, 1):
                    j = self.nearest(ahead, team, outfield=False)
                    tgt[j], urg[j] = ahead, C.CHASE_URGENCY
        elif s.phase == "dead" and s.dead is not None:
            tgt[s.dead.taker], urg[s.dead.taker] = s.dead.spot, C.TAKER_URGENCY
        return tgt, urg

    def move(self) -> None:
        tgt, urg = self.targets()
        pos, vel, energy = step_players(self.pos, self.vel, self.energy, tgt, urg, self.pace,
                                        self.stamina, self.drain)  # fmt: skip
        s = self.s
        if s.phase == "held" and s.owner is not None:
            i = s.owner
            speed = float(np.hypot(*vel[i]))
            if speed > C.DRIBBLE_MAX_MS:
                vel[i] *= C.DRIBBLE_MAX_MS / speed
                pos[i] = self.pos[i] + vel[i] * C.DT
            pos[i] = _clamp(pos[i], 0.3)
        self.pos = np.clip(pos, [-2.0, -2.0], [PITCH_LENGTH + 2.0, PITCH_WIDTH + 2.0])
        self.vel, self.energy = vel, energy

    def at_feet(self, i: int) -> np.ndarray:
        """A carried ball: `BALL_AHEAD_M` ahead of the carrier, inside the pitch."""
        return _clamp(self.pos[i] + _unit(self.vel[i]) * C.BALL_AHEAD_M)

    def update_ball(self) -> None:
        s = self.s
        if s.phase == "held" and s.owner is not None:
            self.ball, self.ball_z = self.at_feet(s.owner), BALL_RADIUS_M
        elif s.phase == "flight" and s.flight is not None:
            f = s.flight
            p = f.traj.positions_at((self.k - f.k0) * C.DT)
            self.ball, self.ball_z = p[:2].copy(), float(p[2])
        elif s.dead is not None:
            self.ball, self.ball_z = s.dead.spot.copy(), BALL_RADIUS_M

    # ---- loop ---------------------------------------------------------------------------

    def setup_period(self, period: Literal[1, 2], added_s: float) -> None:
        self.period = period
        self.n_ticks = round((C.HALF_S + added_s) / C.DT)
        self.s = _State()
        self.events = []
        self.history.clear()
        self.pos = self.kickoff_shape()
        self.spot = self.pos.copy()
        self.vel = np.zeros((22, 2))
        if period == 2:
            self.energy = np.minimum(self.energy + C.HALF_TIME_RECOVERY, 1.0)
        kick_team = 0 if period == 1 else 1
        taker = max(self.members(kick_team), key=lambda j: float(self.anchors[j, 0]))
        self.pos[taker] = CENTRE
        self.k = 0
        self.start_dead(CENTRE.copy(), taker, "kickoff", pause_s=0.0, kickoff=True)

    def tick(self) -> None:
        self.logic()
        self.update_ball()
        self.history.append((self.pos.copy(), self.vel.copy()))
        if self.tracking:
            self.rec_pos.append(self.pos.copy())
            self.rec_vel.append(self.vel.copy())
            self.rec_ball.append((float(self.ball[0]), float(self.ball[1]), self.ball_z))
        self.move()
        self.k += 1

    def finish_period(self) -> None:
        s = self.s
        self.end_carry(True)
        if s.flight is not None:
            self.resolve(s.flight.event, self.ball, False)
        ordered = sorted(self.events, key=lambda e: (e["t"], e["seq"]))
        for ev in ordered:
            if (
                ev["type"] in ("pass", "kickoff", "carry", "clearance", "shot")
                and ev["end"] is None
            ):
                ev["end"], ev["outcome"] = np.array(self.ball), False
            self.all_events.append(self._to_event(ev, len(self.all_events)))
        if self.tracking:
            self.frames += build_frames(self.meta, self.period, len(self.frames), self.rec_pos,
                                        self.rec_vel, self.rec_ball)  # fmt: skip
            self.rec_pos, self.rec_vel, self.rec_ball = [], [], []

    def run_period(self, period: Literal[1, 2], added_s: float) -> None:
        self.setup_period(period, added_s)
        for _ in range(self.n_ticks):
            self.tick()
        self.finish_period()

    def run(self) -> MatchData:
        self.run_period(1, self.meta.added_time_s[0])
        self.run_period(2, self.meta.added_time_s[1])
        meta = self.meta.model_copy(update={"engine_version": ENGINE_VERSION})
        return MatchData(meta=meta, events=self.all_events, frames=self.frames)


def mods_from_profiles(
    meta: MatchMeta, profiles: Profiles
) -> tuple[list[PlayerMods], tuple[TeamMods, TeamMods]]:
    """Kickoff modifiers for both XIs (match-day form drawn from the match seed)."""
    rng = stream(meta.seed, "engine-l3:form")
    clubs = (profiles.clubs[meta.home.club_id], profiles.clubs[meta.away.club_id])
    player_mods = []
    for team, squad in enumerate((meta.home_squad[:11], meta.away_squad[:11])):
        for p in squad:
            prof = profiles.players[p.player_id]
            ctx = MatchContext(is_home=team == 0, form=match_form(prof, rng))
            player_mods.append(Modifiers.for_player(prof, clubs[team], ctx))
    team_mods = (Modifiers.for_team(clubs[0], MatchContext(is_home=True)),
                 Modifiers.for_team(clubs[1], MatchContext(is_home=False)))  # fmt: skip
    return player_mods, team_mods


def simulate_coupled(meta: MatchMeta, tracking: bool = True, profiles: Profiles | None = None
                     ) -> MatchData:  # fmt: skip
    """Level-3 match: same meta (and seed) gives identical events and frames.

    `tracking=False` returns no frames; events are unchanged (recording uses no RNG).
    """
    if profiles is None:
        return Coupled(meta, tracking).run()
    player_mods, team_mods = mods_from_profiles(meta, profiles)
    return Coupled(meta, tracking, player_mods, team_mods).run()
