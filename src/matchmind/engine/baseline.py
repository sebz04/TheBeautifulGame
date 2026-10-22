"""Level-1 engine: formation-anchored players and a Markov possession chain at 10 Hz.

Each tick: (1) on-ball logic decides events from the current positions, (2) the frame is
recorded, (3) players move toward their targets. Off-ball targets are the formation
anchor shifted toward the ball (`BLOCK_SHIFT`) and compressed in width out of
possession (`OUT_OF_POSSESSION_WIDTH`), followed with exponential smoothing. Pass
receivers and carriers follow scripted straight-line paths, so a completed pass ends
exactly where its receiver is. Kept as the fallback engine once level 3 exists.
"""

import gc
import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from matchmind.engine.formations import formation_anchors, to_team_frame
from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH
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

DT = 0.1
HALF_S = 2700.0
BLOCK_SHIFT = 0.35
OUT_OF_POSSESSION_WIDTH = 0.75
SMOOTHING_TAU_S = 0.9
BALL_RADIUS_M = 0.11
MAX_RUN_MS = 8.0  # cap for scripted runs (receivers, carriers)
TACKLE_RANGE_M = 1.5
TACKLE_RATE_PER_TICK = 0.012  # attempt chance per tick while a defender is in range
FOUL_SHARE = 0.2
GAIN_RANGE_M = 1.0
GOAL_PAUSE_S = 45.0
CENTRE = np.array([PITCH_LENGTH / 2, PITCH_WIDTH / 2])

Phase = Literal["held", "flight", "loose", "dead"]
Arrival = Literal["receive", "loose", "out", "goal", "save"]


@dataclass
class _Path:
    start: np.ndarray
    end: np.ndarray
    k0: int
    k1: int

    def at(self, k: int) -> np.ndarray:
        s = min(max((k - self.k0) / max(self.k1 - self.k0, 1), 0.0), 1.0)
        point: np.ndarray = self.start + s * (self.end - self.start)
        return point


@dataclass
class _Flight:
    start: np.ndarray
    end: np.ndarray
    k0: int
    k1: int
    height: float
    arrival: Arrival
    target: int | None  # receiver, keeper, or None
    last_team: int


@dataclass
class _Dead:
    spot: np.ndarray
    taker: int
    resume_k: int
    kickoff: bool
    restart: str


@dataclass
class _State:
    phase: Phase = "dead"
    owner: int | None = None
    poss_team: int = 0
    hold_until: int = 0
    protect_until: int = 0
    reset_shape: bool = False
    restart: str | None = None
    flight: _Flight | None = None
    dead: _Dead | None = None
    loose_spot: np.ndarray | None = None
    loose_team: int = 0
    paths: dict[int, _Path] = field(default_factory=dict)


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _clamp_on_pitch(p: np.ndarray, margin: float = 0.5) -> np.ndarray:
    return np.array(
        [
            min(max(float(p[0]), margin), PITCH_LENGTH - margin),
            min(max(float(p[1]), margin), PITCH_WIDTH - margin),
        ]
    )


class _Baseline:
    def __init__(self, meta: MatchMeta, tracking: bool = True) -> None:
        self.meta = meta
        self.tracking = tracking
        self.rng = stream(meta.seed, "engine-l1")
        self.players = meta.home_squad[:11] + meta.away_squad[:11]
        self.ids = [p.player_id for p in self.players]
        self.team_ids = (meta.home.club_id, meta.away.club_id)
        self.team_of = np.array([0] * 11 + [1] * 11)
        self.anchors = np.vstack(
            [formation_anchors(meta.home.formation), formation_anchors(meta.away.formation)]
        )
        self.skill = np.array([p.skill for p in self.players])
        self.vmax = np.array([5.5 + 2.5 * p.pace for p in self.players])
        self.alpha = 1.0 - math.exp(-DT / SMOOTHING_TAU_S)
        self.events: list[Event] = []
        self.frames: list[TrackingFrame] = []
        self.rec_pos: list[np.ndarray] = []
        self.rec_vel: list[np.ndarray] = []
        self.rec_ball: list[tuple[float, float, float]] = []
        self.period: Literal[1, 2] = 1
        self.k = 0
        self.n_ticks = 0
        self.pos = np.zeros((22, 2))
        self.prev = np.zeros((22, 2))
        self.ball = CENTRE.copy()
        self.ball_z = BALL_RADIUS_M
        self.s = _State()

    # ---- geometry helpers -------------------------------------------------------------

    def attacks_right(self, team: int) -> bool:
        return (team == 0) == (self.period == 1)

    def team_frame(self, xy: np.ndarray, team: int) -> np.ndarray:
        return to_team_frame(xy, self.attacks_right(team))

    def members(self, team: int) -> range:
        return range(0, 11) if team == 0 else range(11, 22)

    def nearest(self, point: np.ndarray, team: int, *, outfield: bool = True) -> int:
        lo = 11 * team + (1 if outfield else 0)
        d = np.hypot(*(self.pos[lo : 11 * team + 11] - point).T)
        return lo + int(np.argmin(d))

    def dist(self, i: int, point: np.ndarray) -> float:
        return float(np.hypot(*(self.pos[i] - point)))

    def nearest_opponent_dist(self, point: np.ndarray, team: int) -> float:
        lo = 11 * (1 - team)
        return float(np.hypot(*(self.pos[lo : lo + 11] - point).T).min())

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
    ) -> None:
        n = len(self.events)
        self.events.append(
            Event(
                event_id=f"{self.meta.match_id}-e{n:05d}",
                match_id=self.meta.match_id,
                period=self.period,
                t=round(self.k * DT, 1),
                type=type_,
                team_id=self.team_ids[team],
                player_id=None if player is None else self.ids[player],
                x=round(float(at[0]), 2),
                y=round(float(at[1]), 2),
                end_x=None if end is None else round(float(end[0]), 2),
                end_y=None if end is None else round(float(end[1]), 2),
                outcome=outcome,
                receiver_id=None if receiver is None else self.ids[receiver],
                ball_speed_ms=speed,
                extras=extras or {},
            )
        )

    # ---- set pieces and possession ---------------------------------------------------------

    def kickoff_shape(self) -> np.ndarray:
        out = np.zeros((22, 2))
        for team in (0, 1):
            idx = list(self.members(team))
            a = self.anchors[idx].copy()
            a[:, 0] = np.minimum(a[:, 0] - 6.0, PITCH_LENGTH / 2 - 1.5)
            a[:, 1] = PITCH_WIDTH / 2 + (a[:, 1] - PITCH_WIDTH / 2) * OUT_OF_POSSESSION_WIDTH
            out[idx] = self.team_frame(a, team)
        return out

    def kicker(self, team: int) -> int:
        return self.members(team)[10]  # the last forward in the XI

    def start_dead(
        self, spot: np.ndarray, taker: int, pause_s: float, restart: str, kickoff: bool = False
    ) -> None:
        self.s.phase = "dead"
        self.s.owner = None
        self.s.flight = None
        self.s.poss_team = int(self.team_of[taker])
        self.s.dead = _Dead(spot, taker, self.k + round(pause_s / DT), kickoff, restart)
        self.ball = spot.copy()
        self.ball_z = BALL_RADIUS_M

    def give_ball(self, i: int, hold_s: float, protect_s: float = 0.0) -> None:
        self.s.phase = "held"
        self.s.owner = i
        self.s.poss_team = int(self.team_of[i])
        self.s.hold_until = self.k + max(1, round(hold_s / DT))
        self.s.protect_until = self.k + round(protect_s / DT)
        self.s.flight = None
        self.s.dead = None
        self.s.loose_spot = None

    def hold_time(self, i: int) -> float:
        if i % 11 == 0:
            return float(self.rng.uniform(2.0, 5.0))
        return 1.5 + float(self.rng.exponential(1.9))

    def resume(self) -> None:
        """The taker is within `GAIN_RANGE_M` of the spot; the ball moves to the taker."""
        dead = self.s.dead
        assert dead is not None
        self.s.reset_shape = False
        if dead.kickoff:
            team = int(self.team_of[dead.taker])
            mids = [j for j in self.members(team) if j not in (dead.taker,) and 5 <= j % 11 <= 8]
            receiver = mids[int(self.rng.integers(len(mids)))]
            self.launch_pass(dead.taker, receiver, kickoff=True)
            return
        self.s.restart = dead.restart
        self.give_ball(dead.taker, float(self.rng.uniform(0.4, 1.2)), protect_s=1.5)

    def restart_after_out(self, at: np.ndarray, last_team: int) -> None:
        on_goal_line = at[0] <= 0.5 or at[0] >= PITCH_LENGTH - 0.5
        if not on_goal_line:
            taker = self.nearest(at, 1 - last_team)
            self.start_dead(at, taker, float(self.rng.uniform(5.0, 8.0)), "throw_in")
            return
        defending = 0 if (at[0] < PITCH_LENGTH / 2) == self.attacks_right(0) else 1
        if last_team == defending:
            corner_y = 0.0 if at[1] < PITCH_WIDTH / 2 else PITCH_WIDTH
            spot = np.array([0.0 if at[0] < PITCH_LENGTH / 2 else PITCH_LENGTH, corner_y])
            taker = self.nearest(spot, 1 - defending)
            self.start_dead(spot, taker, float(self.rng.uniform(15.0, 25.0)), "corner")
        else:
            w = PITCH_WIDTH / 2 + float(self.rng.uniform(-9.0, 9.0))
            spot = self.team_frame(np.array([5.5, w]), defending)
            gk = self.members(defending)[0]
            self.start_dead(spot, gk, float(self.rng.uniform(8.0, 12.0)), "goal_kick")

    # ---- on-ball actions -------------------------------------------------------------------

    def flight_ticks(self, start: np.ndarray, end: np.ndarray, speed: float) -> int:
        return max(2, round(float(np.hypot(*(end - start))) / speed / DT))

    def choose_receiver(self, i: int) -> int | None:
        team = int(self.team_of[i])
        here = self.team_frame(self.pos[i], team)
        best: list[int] = []
        weights: list[float] = []
        for j in self.members(team):
            if j == i:
                continue
            d = self.dist(j, self.pos[i])
            if d < 5.0:
                continue
            gain = float(self.team_frame(self.pos[j], team)[0] - here[0])
            openness = min(self.nearest_opponent_dist(self.pos[j], team), 8.0) / 8.0
            w = math.exp(-(((d - 16.0) / 14.0) ** 2)) * math.exp(0.04 * min(max(gain, -20), 30))
            w *= 0.25 + openness
            if j % 11 == 0:
                w *= 0.15
            best.append(j)
            weights.append(w)
        if not best:
            return None
        p = np.array(weights) / sum(weights)
        return best[int(self.rng.choice(len(best), p=p))]

    def launch_pass(self, i: int, j: int, *, kickoff: bool = False) -> bool:
        team = int(self.team_of[i])
        start = self.pos[i].copy()
        lead = 0.0 if kickoff else float(self.rng.uniform(0.0, 3.0))
        lead_vec = self.team_frame(np.array([lead, 0.0]), team) - self.team_frame(np.zeros(2), team)
        end = _clamp_on_pitch(self.pos[j] + lead_vec + self.rng.normal(0.0, 0.6, 2))
        d = float(np.hypot(*(end - start)))
        speed = min(max(9.0 + 0.3 * d, 9.0), 24.0)
        n = self.flight_ticks(start, end, speed)
        run = self.dist(j, end)
        n = max(n, math.ceil(run / (MAX_RUN_MS * DT)))
        if self.k + n >= self.n_ticks - 1:
            return False
        speed = d / (n * DT)
        press_recv = max(0.0, 1.0 - self.nearest_opponent_dist(end, team) / 5.0)
        press_self = max(0.0, 1.0 - self.nearest_opponent_dist(start, team) / 3.0)
        p_ok = _sigmoid(
            3.0 + 2.0 * (self.skill[i] - 0.5) - 0.045 * d - 1.4 * press_recv - 0.8 * press_self
        )
        if kickoff:
            p_ok = 1.0
        height = 0.0 if d < 22.0 else min(10.0, (d - 22.0) * 0.35)
        type_: EventType = "kickoff" if kickoff else "pass"
        # Work out where the ball goes first; state changes only once the pass is certain
        # to finish before the end of the half.
        receiver: int | None = None
        if self.rng.random() < p_ok:
            flight = _Flight(start, end, self.k, self.k + n, height, "receive", j, team)
            receiver = j
        elif self.rng.random() < 0.18:
            # Overhit: the ball runs out over the nearer touchline.
            side = 0.0 if end[1] < PITCH_WIDTH / 2 else PITCH_WIDTH
            out = np.array([float(end[0]), side])
            n_out = self.flight_ticks(start, out, speed)
            flight = _Flight(start, out, self.k, self.k + n_out, height, "out", None, team)
        else:
            # Intercepted: the ball stops where the best-placed opponent cuts the line.
            seg = end - start
            best_q, best_d = end, math.inf
            for o in self.members(1 - team):
                u = float(np.clip(np.dot(self.pos[o] - start, seg) / max(np.dot(seg, seg), 1e-9),
                                  0.35, 1.0))  # fmt: skip
                q = start + u * seg
                dq = self.dist(o, q)
                if dq < best_d:
                    best_q, best_d = q, dq
            q = _clamp_on_pitch(best_q + self.rng.normal(0.0, 0.8, 2))
            n_q = self.flight_ticks(start, q, speed)
            flight = _Flight(start, q, self.k, self.k + n_q, height, "loose", None, team)
        if flight.k1 >= self.n_ticks - 1:
            return False

        extras: dict[str, object] = {}
        if self.s.restart:
            extras["restart"] = self.s.restart
            self.s.restart = None
        self.s.owner = None
        self.s.phase = "flight"
        self.s.dead = None
        self.s.flight = flight
        if receiver is not None:
            self.s.paths[receiver] = _Path(self.pos[receiver].copy(), end, self.k, flight.k1)
        self.emit(type_, team, i, start, end=flight.end, outcome=receiver is not None,
                  receiver=receiver, speed=round(speed, 3), extras=extras)  # fmt: skip
        return True

    def shoot(self, i: int) -> bool:
        team = int(self.team_of[i])
        here = self.team_frame(self.pos[i], team)
        dx, dy = PITCH_LENGTH - float(here[0]), PITCH_WIDTH / 2 - float(here[1])
        goal_dist = math.hypot(dx, dy)
        cos_angle = dx / max(goal_dist, 1e-6)
        xg = 1.1 * math.exp(-goal_dist / 6.5) * (0.5 + 0.5 * cos_angle)
        xg = min(max(xg * (0.8 + 0.4 * float(self.skill[i])), 0.01), 0.7)
        gk = self.members(1 - team)[0]
        r = self.rng.random()
        arrival: Arrival
        if r < xg:
            w = PITCH_WIDTH / 2 + float(np.clip(self.rng.normal(0, 2.0), -3.4, 3.4))
            end, arrival, target = self.team_frame(np.array([PITCH_LENGTH, w]), team), "goal", None
        elif r < xg + 0.4 * (1 - xg):
            end, arrival, target = self.pos[gk].copy(), "save", gk
        else:
            off = float(self.rng.uniform(4.5, 14.0)) * (1 if self.rng.random() < 0.5 else -1)
            w = min(max(PITCH_WIDTH / 2 + off, 0.5), PITCH_WIDTH - 0.5)
            end, arrival, target = self.team_frame(np.array([PITCH_LENGTH, w]), team), "out", None
        speed = 22.0
        n = self.flight_ticks(self.pos[i], end, speed)
        if self.k + n >= self.n_ticks - 1:
            return False
        start = self.pos[i].copy()
        speed = float(np.hypot(*(end - start))) / (n * DT)
        if target is not None:
            self.s.paths[target] = _Path(self.pos[target].copy(), end, self.k, self.k + n)
        self.s.owner = None
        self.s.phase = "flight"
        self.s.flight = _Flight(start, end, self.k, self.k + n, 1.2, arrival, target, team)
        self.emit("shot", team, i, start, end=end, outcome=arrival == "goal",
                  speed=round(speed, 3), extras={"xg": round(xg, 3)})  # fmt: skip
        return True

    def carry(self, i: int) -> bool:
        team = int(self.team_of[i])
        angle = float(self.rng.normal(0.0, 0.35))
        speed = float(self.rng.uniform(3.5, 5.5))
        dur = float(self.rng.uniform(1.5, 3.5))
        step = np.array([math.cos(angle), math.sin(angle)]) * speed * dur
        here = self.team_frame(self.pos[i], team)
        end = self.team_frame(_clamp_on_pitch(here + step, margin=1.0), team)
        n = max(2, round(dur / DT))
        if self.k + n >= self.n_ticks - 1:
            return False
        self.s.paths[i] = _Path(self.pos[i].copy(), end, self.k, self.k + n)
        self.s.hold_until = self.k + n + round(float(self.rng.uniform(0.3, 0.8)) / DT)
        self.emit("carry", team, i, self.pos[i], end=end, outcome=True)
        return True

    def decide(self, i: int) -> None:
        team = int(self.team_of[i])
        here = self.team_frame(self.pos[i], team)
        goal_dist = math.hypot(PITCH_LENGTH - here[0], PITCH_WIDTH / 2 - here[1])
        is_gk = i % 11 == 0
        p_shot = (
            0.0 if is_gk or goal_dist > 32 else min(0.55, 0.7 * math.exp(-(goal_dist - 10) / 8.5))
        )
        p_carry = 0.0 if is_gk else (0.2 if here[0] > 70 else 0.14)
        r = self.rng.random()
        if r < p_shot and self.shoot(i):
            return
        if r < p_shot + p_carry and self.carry(i):
            return
        j = self.choose_receiver(i)
        if j is None or not self.launch_pass(i, j):
            self.s.hold_until = self.k + 5

    def try_tackle(self, i: int) -> None:
        team = int(self.team_of[i])
        o = self.nearest(self.pos[i], 1 - team)
        if self.dist(o, self.pos[i]) > TACKLE_RANGE_M or self.rng.random() > TACKLE_RATE_PER_TICK:
            return
        at = self.pos[i].copy()
        if self.rng.random() < FOUL_SHARE:
            self.emit("foul", 1 - team, o, at, outcome=None)
            self.s.paths.pop(i, None)
            self.start_dead(at, i, float(self.rng.uniform(6.0, 12.0)), "free_kick")
            return
        won = self.rng.random() < 0.5 + 0.3 * float(self.skill[o] - self.skill[i])
        self.emit("tackle", 1 - team, o, at, outcome=won)
        if won:
            self.s.paths.pop(i, None)
            self.give_ball(o, self.hold_time(o) * 0.6, protect_s=1.0)
        else:
            self.s.protect_until = self.k + round(1.0 / DT)

    # ---- per-tick logic ----------------------------------------------------------------------

    def arrive(self, f: _Flight) -> None:
        self.ball = f.end.copy()
        if f.arrival == "receive":
            assert f.target is not None
            self.give_ball(f.target, self.hold_time(f.target))
        elif f.arrival == "save":
            assert f.target is not None
            self.emit("save", int(self.team_of[f.target]), f.target, f.end, outcome=True)
            self.give_ball(f.target, self.hold_time(f.target))
        elif f.arrival == "goal":
            scorer_event = next(e for e in reversed(self.events) if e.type == "shot")
            scorer = self.ids.index(scorer_event.player_id or "")
            self.emit("goal", f.last_team, scorer, f.end, outcome=True)
            conceding = 1 - f.last_team
            pause = min(GOAL_PAUSE_S, (self.n_ticks - self.k) * DT - 3.0)
            self.s.reset_shape = True
            self.start_dead(CENTRE.copy(), self.kicker(conceding), max(pause, 1.0), "kickoff",
                            kickoff=True)  # fmt: skip
        elif f.arrival == "out":
            self.emit("out", f.last_team, None, f.end)
            self.restart_after_out(f.end, f.last_team)
        else:
            self.s.phase = "loose"
            self.s.flight = None
            self.s.loose_spot = f.end.copy()
            self.s.loose_team = f.last_team

    def logic(self) -> None:
        s = self.s
        if s.phase == "dead":
            assert s.dead is not None
            if self.k >= s.dead.resume_k and self.dist(s.dead.taker, s.dead.spot) <= GAIN_RANGE_M:
                self.resume()
        elif s.phase == "flight":
            assert s.flight is not None
            if self.k >= s.flight.k1:
                self.arrive(s.flight)
        elif s.phase == "loose":
            assert s.loose_spot is not None
            for team in (1 - s.loose_team, s.loose_team):
                j = self.nearest(s.loose_spot, team, outfield=False)
                if self.dist(j, s.loose_spot) <= GAIN_RANGE_M:
                    if team != s.loose_team:
                        self.emit("interception", team, j, self.pos[j], outcome=True)
                    self.give_ball(j, self.hold_time(j) * 0.7, protect_s=0.8)
                    break
        if s.phase == "held":
            assert s.owner is not None
            i = s.owner
            carrying = i in s.paths
            if self.k >= s.protect_until:
                self.try_tackle(i)
            if s.phase == "held" and s.owner == i and not carrying and self.k >= s.hold_until:
                self.decide(i)

    def ball_now(self) -> None:
        s = self.s
        if s.phase == "held" and s.owner is not None:
            self.ball = self.pos[s.owner].copy()
            self.ball_z = BALL_RADIUS_M
        elif s.phase == "flight" and s.flight is not None:
            f = s.flight
            u = min(max((self.k - f.k0) / max(f.k1 - f.k0, 1), 0.0), 1.0)
            self.ball = f.start + u * (f.end - f.start)
            self.ball_z = BALL_RADIUS_M + 4.0 * f.height * u * (1.0 - u)
        else:
            self.ball_z = BALL_RADIUS_M

    def targets(self) -> np.ndarray:
        s = self.s
        if s.reset_shape:
            tgt = self.kickoff_shape()
        else:
            tgt = np.zeros((22, 2))
            for team in (0, 1):
                idx = list(self.members(team))
                b = self.team_frame(self.ball, team)
                poss = s.poss_team == team
                a = self.anchors[idx]
                d = a[:, 0] + BLOCK_SHIFT * (b[0] - CENTRE[0]) + (4.0 if poss else -4.0)
                width = 1.0 if poss else OUT_OF_POSSESSION_WIDTH
                w = CENTRE[1] + (a[:, 1] - CENTRE[1]) * width + BLOCK_SHIFT * (b[1] - CENTRE[1])
                d[0] = min(max(5.0 + 0.08 * (b[0] - CENTRE[0]), 1.0), 16.0)
                w[0] = CENTRE[1] + 0.12 * (b[1] - CENTRE[1])
                local = np.column_stack(
                    [np.clip(d, 1.0, PITCH_LENGTH - 1), np.clip(w, 1.0, PITCH_WIDTH - 1)]
                )
                tgt[idx] = self.team_frame(local, team)
        if s.phase == "held" and s.owner is not None:
            i = s.owner
            team = int(self.team_of[i])
            fwd = self.team_frame(np.array([1.2, 0.0]), team) - self.team_frame(np.zeros(2), team)
            tgt[i] = _clamp_on_pitch(self.pos[i] + fwd)
            presser = self.nearest(self.pos[i], 1 - team)
            own_goal = self.team_frame(np.array([0.0, CENTRE[1]]), 1 - team)
            v = own_goal - self.pos[i]
            tgt[presser] = self.pos[i] + 1.2 * v / max(float(np.hypot(*v)), 1e-6)
        elif s.phase == "loose" and s.loose_spot is not None:
            for team in (0, 1):
                tgt[self.nearest(s.loose_spot, team, outfield=False)] = s.loose_spot
        elif s.phase == "dead" and s.dead is not None:
            tgt[s.dead.taker] = s.dead.spot
        return tgt

    def move(self) -> None:
        s = self.s
        tgt = self.targets()
        delta = tgt - self.pos
        step = self.alpha * delta
        full_speed: list[int] = []
        if s.phase == "loose" and s.loose_spot is not None:
            full_speed = [self.nearest(s.loose_spot, t, outfield=False) for t in (0, 1)]
        elif s.phase == "dead" and s.dead is not None:
            full_speed = [s.dead.taker]
        if s.owner is not None:
            full_speed.append(s.owner)
        step[full_speed] = delta[full_speed]
        cap = self.vmax * DT
        if s.owner is not None:
            cap = cap.copy()
            cap[s.owner] = 1.2 * DT
        norm = np.hypot(step[:, 0], step[:, 1])
        scale = np.where(norm > cap, cap / np.maximum(norm, 1e-12), 1.0)
        new = self.pos + step * scale[:, None]
        for i, path in list(s.paths.items()):
            new[i] = path.at(self.k + 1)
            if self.k + 1 >= path.k1:
                del s.paths[i]
        self.prev, self.pos = self.pos, new

    def record(self) -> None:
        self.rec_pos.append(self.pos.copy())
        self.rec_vel.append((self.pos - self.prev) / DT)
        self.rec_ball.append((float(self.ball[0]), float(self.ball[1]), float(self.ball_z)))

    def flush_frames(self) -> None:
        self.frames += build_frames(
            self.meta, self.period, len(self.frames), self.rec_pos, self.rec_vel, self.rec_ball
        )
        self.rec_pos, self.rec_vel, self.rec_ball = [], [], []

    def run_period(self, period: Literal[1, 2], added_s: float) -> None:
        self.period = period
        self.n_ticks = round((HALF_S + added_s) / DT)
        self.s = _State()
        self.pos = self.kickoff_shape()
        kick_team = 0 if period == 1 else 1
        taker = self.kicker(kick_team)
        self.pos[taker] = CENTRE
        self.prev = self.pos.copy()
        self.k = 0
        self.start_dead(CENTRE.copy(), taker, 0.0, "kickoff", kickoff=True)
        for k in range(self.n_ticks):
            self.k = k
            self.logic()
            self.ball_now()
            if self.tracking:
                self.record()
            self.move()
        if self.tracking:
            self.flush_frames()

    def run(self) -> MatchData:
        for period, added in ((1, self.meta.added_time_s[0]), (2, self.meta.added_time_s[1])):
            self.run_period(period, added)  # type: ignore[arg-type]
        return MatchData(meta=self.meta, events=self.events, frames=self.frames)


def build_frames(
    meta: MatchMeta,
    period: Literal[1, 2],
    first_frame: int,
    rec_pos: list[np.ndarray],
    rec_vel: list[np.ndarray],
    rec_ball: list[tuple[float, float, float]],
) -> list[TrackingFrame]:
    """One period's recorded (22, 2) positions and velocities and ball points as
    `TrackingFrame`s, rounded to 1 cm. Players are the two starting XIs, home first.

    The cyclic GC is paused while about 650k small objects are created: they hold no
    cycles, and repeated full collections would otherwise dominate the run time.
    """
    enabled = gc.isenabled()
    gc.disable()
    try:
        return _build_frames(meta, period, first_frame, rec_pos, rec_vel, rec_ball)
    finally:
        if enabled:
            gc.enable()


def _build_frames(
    meta: MatchMeta,
    period: Literal[1, 2],
    first_frame: int,
    rec_pos: list[np.ndarray],
    rec_vel: list[np.ndarray],
    rec_ball: list[tuple[float, float, float]],
) -> list[TrackingFrame]:
    if not rec_pos:
        return []
    ids = [p.player_id for p in meta.home_squad[:11] + meta.away_squad[:11]]
    teams = [meta.home.club_id] * 11 + [meta.away.club_id] * 11
    pos = np.round(np.stack(rec_pos), 2).tolist()
    vel = np.round(np.stack(rec_vel), 2).tolist()
    ball = np.round(np.array(rec_ball), 2).tolist()
    frames: list[TrackingFrame] = []
    for k, (p_k, v_k, b_k) in enumerate(zip(pos, vel, ball, strict=True)):
        players = [
            trusted(
                PlayerPos,
                {
                    "player_id": ids[i],
                    "team_id": teams[i],
                    "x": p_k[i][0],
                    "y": p_k[i][1],
                    "vx": v_k[i][0],
                    "vy": v_k[i][1],
                },
            )
            for i in range(22)
        ]
        frames.append(
            trusted(
                TrackingFrame,
                {
                    "match_id": meta.match_id,
                    "frame": first_frame + k,
                    "period": period,
                    "t": round(k * DT, 1),
                    "ball": (b_k[0], b_k[1], b_k[2]),
                    "players": players,
                },
            )
        )
    return frames


def simulate_baseline(meta: MatchMeta, tracking: bool = True) -> MatchData:
    """Level-1 match: same meta (and seed) gives identical events and frames.

    `tracking=False` returns no frames; events are unchanged (recording uses no RNG).
    """
    return _Baseline(meta, tracking).run()
