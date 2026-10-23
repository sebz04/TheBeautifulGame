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

import dataclasses
import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
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
    pair_mods,
)
from matchmind.engine.pitch import PITCH_LENGTH, PITCH_WIDTH
from matchmind.engine.realism_ranges import SPRINT_MIN_S, SPRINT_SPEED_MS
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
from matchmind.engine.scenario import Scenario
from matchmind.engine.set_pieces import (
    BOX_DEPTH_M,
    FK_MAX_M,
    FK_MIN_M,
    PENALTY_CONVERSION,
    PENALTY_SPOT,
    aerial_duel,
    corner_delivery,
    free_kick_xg,
    header_xg,
    in_box,
    keeper_claims,
    penalty_scores,
)
from matchmind.engine.tactics import (
    Phase,
    formation_shape,
    runs_in_behind_rate,
    shape_lines,
    trigger,
)
from matchmind.league.dist import stream
from matchmind.league.profiles import chemistry
from matchmind.schemas import (
    Event,
    EventType,
    MatchData,
    MatchMeta,
    Player,
    PlayerPos,
    TrackingFrame,
    trusted,
)
from matchmind.schemas_profile import ClubProfile, Profiles
from matchmind.stats.pitch_control import offside_players
from matchmind.stats.xt import load_xt

ENGINE_VERSION = "l4-0.1"  # the level-3 loop with level-4 tactics, set pieces, scenarios
CENTRE = np.array([PITCH_LENGTH / 2, PITCH_WIDTH / 2])
SPRINT_TICKS = round(SPRINT_MIN_S / C.DT)
Chooser = Callable[[list[Option]], Option]
EventDict = dict[str, Any]
_PASS_ONLY = {"throw_in", "kickoff", "goal_kick", "corner"}
_NO_OFFSIDE = {"throw_in", "goal_kick", "corner"}


@dataclass
class Motion:
    """A player's running for one match, tallied at 10 Hz as the frames would show it."""

    distance_m: float = 0.0
    top_speed_ms: float = 0.0
    sprints: int = 0  # above SPRINT_SPEED_MS for at least SPRINT_MIN_S
    minutes: float = 0.0


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
    set_piece: str | None = None  # carried by the shot and its deflections
    shot_event: EventDict | None = None  # the shot, marked a goal if this ball goes in
    header: bool = False  # a corner delivery: the winner of the duel heads it


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
    won_k: int = -(10**6)  # tick the team in possession won the ball in open play
    trigger_until: list[int] = field(default_factory=lambda: [0, 0])  # per pressing team


def _with_tactics(tm: TeamMods, overrides: dict[str, float]) -> TeamMods:
    """Team mods with tactics changed by scenario beats."""
    return dataclasses.replace(
        tm,
        press_intensity=overrides.get("press_intensity", tm.press_intensity),
        line_height=overrides.get("line_height", tm.line_height),
        tempo=overrides.get("tempo", tm.tempo),
        width=overrides.get("width", tm.width),
        directness=overrides.get("directness", tm.directness),
    )


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
        profiles: Profiles | None = None,
        xt: np.ndarray | None = None,
        scenario: Scenario | None = None,
    ) -> None:
        self.meta = meta
        self.beats = list(scenario.beats) if scenario is not None else []
        self.tracking = tracking
        self.rng = stream(meta.seed, "engine-l3")
        self.players = meta.home_squad[:11] + meta.away_squad[:11]
        self.ids = [p.player_id for p in self.players]
        self.team_ids = (meta.home.club_id, meta.away.club_id)
        self.team_of = np.array([0] * 11 + [1] * 11)
        self.anchors = np.vstack(
            [formation_anchors(meta.home.formation), formation_anchors(meta.away.formation)]
        )
        self.profiles = profiles
        self.form_rng = stream(meta.seed, "engine-l3:form")
        n = 22
        self.is_df, self.is_fw = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
        self.skill, self.pace, self.stamina = np.zeros(n), np.zeros(n), np.zeros(n)
        self.aerial, self.crossing, self.finishing = np.zeros(n), np.zeros(n), np.zeros(n)
        self.height = np.zeros(n)
        self.form = np.zeros(n)
        self.roles: list[str | None] = [None] * n
        for slot, player in enumerate(self.players):
            self.load_slot(slot, player)
        self.goalkeepers = frozenset({self.ids[0], self.ids[11]})
        self.bench = (list(meta.home_squad[11:]), list(meta.away_squad[11:]))
        self.subs_used = [0, 0]
        self.subs_due: list[list[int | None]] = [[], []]  # pending subs (beat: position slot)
        self.auto_subs_done = [0, 0]
        self.overrides: tuple[dict[str, float], dict[str, float]] = ({}, {})
        self.storyline_until = [-1.0, -1.0]  # match seconds
        self.goal_boost_until = [-1.0, -1.0]
        self.pending_red = [False, False]
        self.yellows: dict[str, int] = {}
        self.score = [0, 0]
        self.clubs: tuple[ClubProfile | None, ClubProfile | None] = (None, None)
        if profiles is not None:
            self.clubs = (profiles.clubs[meta.home.club_id], profiles.clubs[meta.away.club_id])
        self.pmods: list[PlayerMods] = [PlayerMods() for _ in range(n)]
        self.tmods: tuple[TeamMods, TeamMods] = (TeamMods(), TeamMods())
        self.update_mods()
        self.chem: dict[tuple[str, str], float] = {}
        if profiles is not None:
            for team, squad in enumerate((meta.home_squad, meta.away_squad)):
                club = self.clubs[team]
                assert club is not None
                profs = [profiles.players[p.player_id] for p in squad]
                self.chem.update(chemistry(profs, club.management.manager_tenure_years))
        self.rosters: list[tuple[str | None, ...]] = []
        self.rec_roster: list[int] = []
        self.formations = (meta.home.formation, meta.away.formation)
        self.active = np.ones(22, dtype=bool)  # False once sent off
        self.xt = load_xt() if xt is None else xt
        self.energy = np.array([min(1.0, m.start_energy) for m in self.pmods])
        self.sent_off: set[int] = set()
        self.motion: dict[str, Motion] = {}
        self._dist, self._top = np.zeros(22), np.zeros(22)
        self._sprints, self._ticks, self._run = (
            np.zeros(22, int),
            np.zeros(22, int),
            np.zeros(22, int),
        )
        self._last = np.full((22, 2), np.nan)
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

    # ---- players and modifiers ----------------------------------------------------------

    def load_slot(self, slot: int, player: Player) -> None:
        """Put `player` in `slot` (kickoff or a substitution): ratings, role, form."""
        self.players[slot] = player
        self.ids[slot] = player.player_id
        self.is_df[slot], self.is_fw[slot] = player.position == "DF", player.position == "FW"
        self.skill[slot], self.pace[slot] = player.skill, player.pace
        self.stamina[slot] = player.stamina
        prof = None if self.profiles is None else self.profiles.players[player.player_id]
        if prof is None:
            self.aerial[slot] = self.crossing[slot] = self.finishing[slot] = player.skill
            self.height[slot] = C.DEFAULT_HEIGHT_CM
            self.roles[slot], self.form[slot] = None, 0.0
        else:
            tec = prof.technical
            self.aerial[slot], self.crossing[slot] = tec.aerial, tec.crossing
            self.finishing[slot] = tec.finishing
            self.height[slot] = prof.status.height_cm
            self.roles[slot] = prof.style.role
            self.form[slot] = match_form(prof, self.form_rng)

    def pair_chemistry(self, i: int, j: int) -> float:
        a, b = sorted((self.ids[i], self.ids[j]))
        return self.chem.get((a, b), 0.5)

    def pair_completion(self, i: int, j: int) -> float:
        """Pass completion multiplier for passer i and receiver j (chemistry, capped)."""
        if not self.chem:
            return 1.0
        team = int(self.team_of[i])
        story = self.match_s() <= self.storyline_until[team] if self.n_ticks else False
        return pair_mods(self.pair_chemistry(i, j), story).completion

    def minute(self) -> float:
        return (0.0 if self.period == 1 else 45.0) + self.k * C.DT / 60.0

    def match_s(self) -> float:
        return self.minute() * 60.0

    def update_mods(self) -> None:
        """Modifiers for the current minute, score, energy, and storyline windows."""
        if self.profiles is None:
            self.tmods = (_with_tactics(TeamMods(), self.overrides[0]),
                          _with_tactics(TeamMods(), self.overrides[1]))  # fmt: skip
            self.drain = np.ones(22)
            return
        now = self.match_s() if getattr(self, "n_ticks", 0) else 0.0
        energy = getattr(self, "energy", np.ones(22))
        for team in (0, 1):
            club = self.clubs[team]
            assert club is not None
            story = now <= self.storyline_until[team]
            diff = self.score[team] - self.score[1 - team]
            for slot in self.members(team):
                prof = self.profiles.players[self.ids[slot]]
                ctx = MatchContext(minute=now / 60.0, score_diff=diff, is_home=team == 0,
                                   energy=float(energy[slot]), storyline=story,
                                   form=float(self.form[slot]))  # fmt: skip
                self.pmods[slot] = Modifiers.for_player(prof, club, ctx)
            ctx = MatchContext(minute=now / 60.0, score_diff=diff, is_home=team == 0,
                               storyline=story)  # fmt: skip
            tm = Modifiers.for_team(club, ctx)
            tm = _with_tactics(tm, self.overrides[team])
            self.tmods = (tm, self.tmods[1]) if team == 0 else (self.tmods[0], tm)
        self.drain = np.array([m.energy_drain for m in self.pmods])

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

    def on(self, team: int) -> list[int]:
        """Slots of the team still on the pitch."""
        return [j for j in self.members(team) if self.active[j]]

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
        d = np.where(self.active[lo : 11 * team + 11], d, np.inf)
        return lo + int(np.argmin(d))

    def frame(self, lagged: bool = False) -> TrackingFrame:
        pos, vel = self.history[0] if lagged and self.history else (self.pos, self.vel)
        players = [
            trusted(PlayerPos, {"player_id": self.ids[i], "team_id": self.team_ids[i // 11],
                                "x": float(pos[i, 0]), "y": float(pos[i, 1]),
                                "vx": float(vel[i, 0]), "vy": float(vel[i, 1])})
            for i in range(22) if self.active[i]
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
            "receiver": None if receiver is None else self.ids[receiver],
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
        ev["receiver"] = None if receiver is None else self.ids[receiver]
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
            receiver_id=receiver,
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
            if s.phase != "dead":
                s.won_k = self.k
        s.phase, s.owner, s.poss_team = "held", i, int(self.team_of[i])
        s.decide_k = self.k + max(1, round(hold_s / C.DT))
        s.protect_until = self.k + round(protect_s / C.DT)
        s.flight, s.dead, s.carry_end = None, None, None
        self.schedule_run()

    def pick_runner(self, team: int) -> int | None:
        fws = [j for j in self.on(team) if self.is_fw[j] and j != self.s.owner]
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
        window_min = max(s.decide_k - self.k, 1) * C.DT / 60.0
        if self.rng.random() >= 1.0 - math.exp(-self.run_rate(team, s.runner) * window_min):
            s.run_start_k = None  # no run this time: he holds the line
            return
        sd = RUN_TIMING_SD_S * self.pmods[s.runner].run_timing_sd
        self.set_run(s.runner, float(self.rng.normal(0.0, sd)))

    def run_rate(self, team: int, runner: int) -> float:
        """Runs per minute in possession (`tactics.runs_in_behind_rate`)."""
        club = self.clubs[team]
        line = self.tmods[1 - team].line_height
        pace = float(self.pace[runner])
        if club is None:
            return C.RUN_RATE_BASE * (0.7 + 0.6 * pace) * (0.5 + line)
        return runs_in_behind_rate(club, self.roles[runner], line, pace)

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
            mids = [j for j in self.on(team) if j != dead.taker and not self.is_df[j]
                    and not self.is_fw[j] and j % 11 != 0]  # fmt: skip
            mids = mids or [j for j in self.on(team) if j not in (dead.taker, 11 * team)]
            j = mids[int(self.rng.integers(len(mids)))]
            opt = Option("pass", self.ids[j], (float(self.pos[j, 0]), float(self.pos[j, 1])),
                         0.0)  # fmt: skip
            s.restart = None
            self.kick(dead.taker, opt, {}, type_="kickoff", sure=True)
        elif dead.restart == "penalty":
            self.take_penalty(dead.taker)
        elif dead.restart == "corner" and self.rng.random() >= C.SHORT_CORNER_SHARE:
            self.deliver_corner(dead.taker)
        elif dead.restart == "free_kick":
            team = int(self.team_of[dead.taker])
            local = self.local(dead.spot, team)
            dist = float(np.hypot(PITCH_LENGTH - local[0], CENTRE[1] - local[1]))
            xg = free_kick_xg(dist, float(self.finishing[dead.taker]))
            if xg > 0.0 and not in_box(local) and self.rng.random() < C.DIRECT_FK_SHARE:
                s.restart = None
                extras: dict[str, object] = {"restart": "free_kick", "set_piece": "free_kick"}
                skill = float(self.skill[dead.taker])
                loft = float(self.rng.uniform(*C.FREE_KICK_LOFT_DEG))
                self.shoot(dead.taker, extras, xg / (0.85 + 0.3 * skill), loft=loft)

    def take_penalty(self, i: int) -> None:
        """About 76% go in (composure nudges it); misses are saved or go wide."""
        s = self.s
        s.restart = None
        team = int(self.team_of[i])
        composure = 1.0 / self.pmods[i].decision_temperature
        side = 1.0 if self.rng.random() < 0.5 else -1.0
        scores = penalty_scores(self.rng, composure)
        saved = not scores and self.rng.random() < C.PENALTY_SAVE_SHARE
        wide = (4.2, 6.0) if not (scores or saved) else (0.8, 3.0)
        y = CENTRE[1] + side * float(self.rng.uniform(*wide))
        start = self.ball.copy()
        aim = self.local(np.array([PITCH_LENGTH + 3.0, y]), team)
        speed = float(self.rng.uniform(*C.PENALTY_SPEED_MS))
        traj = flight(start, aim, "shot", speed, loft_deg=float(self.rng.uniform(1.0, 5.0)))
        extras = {"restart": "penalty", "set_piece": "penalty", "xg": PENALTY_CONVERSION}
        ev = self.emit("shot", team, i, start, speed=round(speed, 2), extras=extras)
        never = self.k + len(traj.t) + 1
        f = _Flight(traj, self.k, team, i, None, never, never, ev, shooter=i, is_shot=True,
                    set_piece="penalty", shot_event=ev)  # fmt: skip
        if saved and traj.out is not None:
            k_save = self.k + max(1, math.floor((traj.out[0] - C.SAVE_LEAD_S) / C.DT))
            f.shot = _ShotPlan("save", k_save, 11 * (1 - team), catch=False)
        self.launch(f)

    def corner_attackers(self, team: int, taker: int) -> list[int]:
        outfield = [j for j in self.on(team) if j % 11 != 0 and j != taker]
        ranked = sorted(outfield, key=lambda j: -(self.aerial[j] + self.height[j] / 200.0))
        return ranked[: C.CORNER_ATTACKERS]

    def deliver_corner(self, i: int) -> None:
        """A cross into the box: the keeper claims it, or the attacker and defender nearest
        the drop contest it in the air (`set_pieces.aerial_duel`)."""
        s = self.s
        s.restart = None
        team = int(self.team_of[i])
        corner_local = self.local(self.ball, team)
        landing_local = corner_delivery(
            self.rng, float(self.crossing[i]), corner_local[1] < CENTRE[1]
        )
        landing = self.local(landing_local, team)
        gk = 11 * (1 - team)
        attackers = self.corner_attackers(team, i)
        att = min(attackers, key=lambda j: self.dist(j, landing)) if attackers else None
        defenders = [j for j in self.on(1 - team) if j != gk]
        dfd = min(defenders, key=lambda j: self.dist(j, landing))
        if keeper_claims(self.rng, landing_local, float(self.aerial[gk])):
            winner = gk
        elif att is not None and aerial_duel(
            self.rng,
            float(self.aerial[att]),
            float(self.height[att]),
            float(self.aerial[dfd]),
            float(self.height[dfd]),
        ):
            winner = att
        else:
            winner = dfd
        start = self.ball.copy()
        d = float(np.hypot(*(landing - start)))
        speed = draw_speed(self.rng, "lofted", d, float(self.skill[i]))
        traj = flight(start, landing, "lofted", speed)
        extras: dict[str, object] = {"restart": "corner", "set_piece": "corner"}
        ev = self.emit("pass", team, i, start, speed=round(speed, 2), extras=extras)
        arrive = round(traj.duration / C.DT)
        collect_from = self.k + max(1, arrive - 4)
        free = self.k + round((traj.duration + C.FREE_AFTER_S) / C.DT)
        self.launch(_Flight(traj, self.k, team, i, winner, collect_from, free, ev, att,
                            header=True, set_piece="corner"))  # fmt: skip

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
            if f.shot_event is not None:
                f.shot_event["outcome"] = True
        else:
            scorer = f.last_player if f.last_team == scoring else None
            if scorer is not None:
                # A pass or cross that goes straight in still counts as a shot.
                start = f.traj.xyz[0, :2]
                xg = shot_xg(start, self.right(scoring), float(self.skill[scorer]))
                self.emit("shot", scoring, scorer, start, end=point, outcome=True,
                          extras={"xg": round(xg, 3), "from_pass": True})  # fmt: skip
        own_goal = scorer is None
        extras: dict[str, object] = {"own_goal": True} if own_goal else {}
        if f.set_piece:
            extras["set_piece"] = f.set_piece
        self.emit("goal", scoring, scorer, point, outcome=True, extras=extras)
        self.score[scoring] += 1
        self.update_mods()
        pause = min(C.GOAL_PAUSE_S, (self.n_ticks - self.k) * C.DT - 3.0)
        self.s.reset_shape = True
        conceding = 1 - scoring
        taker = max(self.on(conceding), key=lambda j: float(self.anchors[j, 0]))
        self.start_dead(CENTRE.copy(), taker, "kickoff", pause_s=max(pause, 1.0), kickoff=True)

    # ---- on-ball actions ----------------------------------------------------------------

    def decide(self, i: int) -> None:
        s = self.s
        team = int(self.team_of[i])
        self.end_carry(True)
        boosted = self.match_s() <= self.goal_boost_until[team]
        ctx = DecisionContext(
            self.team_ids[team],
            self.right(team),
            self.xt,
            self.goalkeepers,
            risk_weight=self.pmods[i].risk_weight,
            shot_cost=C.GOAL_BEAT_SHOT_COST if boosted else C.SHOT_COST,
            clear_bonus=C.CLEAR_BONUS,
            keep_weight=C.GOAL_BEAT_KEEP_WEIGHT if boosted else C.SHOT_KEEP_WEIGHT,
        )
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
            self.shoot(i, extras, opt.pc_prob)
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
        opp = np.array(self.on(1 - team))
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
        if target is not None and not sure:
            p_ok = min(p_ok * self.pair_completion(i, target), 1.0)
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

    def shoot(self, i: int, extras: dict[str, object], base_xg: float, *,
              loft: float | None = None, speed: float | None = None) -> None:  # fmt: skip
        """`base_xg`: the option's xG (pressure included, average skill)."""
        team = int(self.team_of[i])
        skill = float(self.skill[i])
        start = self.ball.copy()
        xg = base_xg * (0.85 + 0.3 * skill)
        boosted = self.match_s() <= self.goal_boost_until[team]
        if boosted:
            xg *= C.GOAL_BEAT_XG_MULT
        xg = min(xg, 0.95)
        aim_local = np.array([PITCH_LENGTH, PITCH_WIDTH / 2 + float(self.rng.uniform(
            -(3.66 - C.SHOT_AIM_INSIDE_M), 3.66 - C.SHOT_AIM_INSIDE_M))])  # fmt: skip
        aim = self.local(aim_local, team)
        err = C.SHOT_ERR_DEG * (1.5 - skill) * self.pmods[i].shot_error
        err *= C.GOAL_BEAT_AIM if boosted else 1.0
        angle = math.atan2(aim[1] - start[1], aim[0] - start[0])
        angle += math.radians(float(self.rng.normal(0.0, err)))
        d = float(np.hypot(*(aim - start)))
        target = start + (d + 3.0) * np.array([math.cos(angle), math.sin(angle)])
        speed = draw_speed(self.rng, "shot", d, skill) if speed is None else speed
        loft = float(self.rng.uniform(*C.SHOT_LOFT_DEG)) if loft is None else loft
        traj = flight(start, target, "shot", speed, loft_deg=loft)
        extras = {**extras, "xg": round(xg, 3)}
        ev = self.emit("shot", team, i, start, speed=round(speed, 2), extras=extras)
        never = self.k + len(traj.t) + 1
        f = _Flight(traj, self.k, team, i, None, never, never, ev, shooter=i, is_shot=True,
                    shot_event=ev)  # fmt: skip
        f.set_piece = str(extras["set_piece"]) if "set_piece" in extras else None
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
        for o in self.on(1 - team):
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
        # On-target shots score about xg / ON_TARGET_SHARE, so goals track xG on average.
        p_save = 1.0 - C.SAVE_XG * xg + C.SAVE_SKILL * (float(self.skill[gk]) - 0.5)
        p_save = min(max(p_save / self.pmods[gk].gk_error, C.SAVE_RANGE[0]), C.SAVE_RANGE[1])
        if self.match_s() <= self.goal_boost_until[team]:
            p_save *= C.GOAL_BEAT_SAVE
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
                            shooter=f.shooter, set_piece=f.set_piece,
                            shot_event=f.shot_event))  # fmt: skip

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
        booked = C.BOOKED_CAUTION if self.yellows.get(self.ids[o], 0) else 1.0
        rate = C.TACKLE_RATE_PER_TICK * self.pmods[o].tackle_rate * booked
        if self.pending_red[1 - team]:
            rate *= C.PENDING_RED_TACKLE_MULT
        if self.rng.random() > rate:
            return
        at = self.ball.copy()
        careful = C.BOX_FOUL_FACTOR if in_box(self.local(np.array(at), team)) else 1.0
        foul = self.rng.random() < C.FOUL_SHARE * careful * booked * self.pmods[o].foul_rate
        if foul or self.pending_red[1 - team]:
            self.award_foul(o, i, at)
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

    def award_foul(self, fouler: int, victim: int, at: np.ndarray) -> None:
        """A foul by `fouler` on `victim` at `at`: card, then a penalty (in the box) or a
        free kick (a direct-shot specialist takes it within 30 m of goal)."""
        team = int(self.team_of[victim])
        mods = self.pmods[fouler].to_extras(("foul_rate", "tackle_rate"))
        self.emit("foul", 1 - team, fouler, at, extras={"mods": mods})
        self.book(fouler, at)
        local = self.local(np.array(at[:2]), team)
        if in_box(local):
            spot = self.local(np.array(PENALTY_SPOT), team)
            taker = max(self.on(team), key=lambda j: (j % 11 != 0, self.finishing[j]))
            pause = float(self.rng.uniform(*C.PENALTY_PAUSE_S))
            self.start_dead(spot, taker, "penalty", pause_s=pause)
            return
        goal_dist = float(np.hypot(PITCH_LENGTH - local[0], CENTRE[1] - local[1]))
        taker = victim
        if FK_MIN_M <= goal_dist <= FK_MAX_M:
            outfield = [j for j in self.on(team) if j % 11 != 0]
            taker = max(outfield, key=lambda j: self.finishing[j])
        self.start_dead(_clamp(at, 0.5), taker, "free_kick")

    def book(self, fouler: int, at: np.ndarray) -> None:
        """Yellow or red card for a foul; a pending red-card beat makes it a red."""
        team = int(self.team_of[fouler])
        pid = self.ids[fouler]
        outfield = fouler % 11 != 0
        if self.pending_red[team] and outfield:
            card = "red"
            self.pending_red[team] = False
        else:
            r = self.rng.random()
            aggression = self.pmods[fouler].foul_rate
            if r < C.RED_SHARE * aggression and outfield:
                card = "red"
            elif r < C.YELLOW_SHARE * aggression:
                card = "yellow"
            else:
                return
        self.emit("card", team, fouler, at, extras={"card": card})
        if card == "yellow":
            self.yellows[pid] = self.yellows.get(pid, 0) + 1
            if self.yellows[pid] < 2 or not outfield:
                return
            self.emit("card", team, fouler, at, extras={"card": "red", "second_yellow": True})
        self.send_off(fouler)

    def send_off(self, slot: int) -> None:
        self.flush_motion(slot)
        self.active[slot] = False
        self.sent_off.add(slot)
        self.pos[slot], self.vel[slot] = C.OFF_PITCH, 0.0
        self.spot[slot] = C.OFF_PITCH
        if self.s.runner == slot:
            self.s.runner = None
        self.record_roster()

    def record_roster(self) -> None:
        roster = tuple(pid if self.active[j] else None for j, pid in enumerate(self.ids))
        self.rosters.append(roster)

    def substitute(self, team: int, position_slot: int | None = None) -> bool:
        """The most tired outfield player (or the one in `position_slot`) makes way for the
        best bench player of the same position."""
        if self.subs_used[team] >= C.MAX_SUBS:
            return False
        outfield = [j for j in self.on(team) if j % 11 != 0]
        if not outfield:
            return False
        if position_slot in outfield:
            out = position_slot
        else:
            out = min(outfield, key=lambda j: float(self.energy[j]))
        position = self.players[out].position
        bench = [p for p in self.bench[team] if p.position == position] or [
            p for p in self.bench[team] if p.position != "GK"
        ]
        if not bench:
            return False
        incoming = max(bench, key=lambda p: (p.skill, p.player_id))
        self.bench[team].remove(incoming)
        ev = self.emit("sub", team, out, self.pos[out], extras={"minute": round(self.minute(), 1)})
        ev["receiver"] = incoming.player_id
        self.flush_motion(out)
        self.load_slot(out, incoming)
        self.energy[out] = 1.0
        self.subs_used[team] += 1
        self.update_mods()
        self.record_roster()
        return True

    def apply_beats(self) -> None:
        """Beats whose minute has come (see `engine/scenario.py`)."""
        now = self.minute()
        while self.beats and self.beats[0].minute <= now:
            beat = self.beats.pop(0)
            team = 0 if beat.team == "home" else 1
            self.storyline_until[team] = self.match_s() + C.STORYLINE_WINDOW_S
            if beat.kind == "red_card":
                self.pending_red[team] = True
            elif beat.kind == "goal":
                self.goal_boost_until[team] = self.match_s() + C.GOAL_BEAT_WINDOW_S
            elif beat.kind == "sub":
                slot = beat.params.get("slot")
                self.subs_due[team].append(None if slot is None else 11 * team + int(slot))
            elif beat.kind == "tactic_change":
                self.overrides[team].update({k: float(v) for k, v in beat.params.items()})
            elif beat.kind == "press_intensity":
                self.overrides[team]["press_intensity"] = float(beat.params.get("value", 1.0))
            else:  # fatigue_spike
                amount = float(beat.params.get("amount", C.FATIGUE_SPIKE))
                for j in self.on(team):
                    self.energy[j] = max(self.energy[j] - amount, 0.0)
            self.update_mods()

    def match_flow(self) -> None:
        """Once a tick: beats, managers' substitutions (at stoppages), modifier refresh."""
        self.apply_beats()
        if self.k % round(C.MOD_UPDATE_S / C.DT) == 0:
            self.update_mods()
        for team in (0, 1):
            done = self.auto_subs_done[team]
            if done < len(C.AUTO_SUB_MINUTES) and self.minute() >= C.AUTO_SUB_MINUTES[done]:
                self.auto_subs_done[team] += 1
                self.subs_due[team].append(None)
            if self.subs_due[team] and self.s.phase == "dead":
                self.substitute(team, self.subs_due[team].pop(0))

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
            self.press_trigger(1 - team, "poor_touch")
            return
        if f.header and j % 11 != 0:
            if team == f.last_team:
                self.resolve(f.event, at, True, j)
                self.ball = np.array(at[:2], dtype=float)
                xg = header_xg(self.local(self.ball, team), self.right(team))
                header: dict[str, object] = {"set_piece": "corner", "header": True}
                base = xg / (0.85 + 0.3 * float(self.skill[j]))
                loft = float(self.rng.uniform(-2.0, 6.0))
                self.shoot(j, header, base, loft=loft, speed=C.HEADER_SPEED_MS)
            else:
                self.resolve(f.event, at, False)
                self.emit("clearance", team, j, at, extras={"header": True, "deflection": True})
                self.deflected(f, at, j, "block", safe=True)
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
        if team == f.last_team:
            ev = f.event
            back = False
            if ev is not None and ev["type"] == "pass" and ev["end"] is not None:
                end_depth = float(self.local(ev["end"], team)[0])
                gain = end_depth - float(self.local(ev["at"], team)[0])
                back = gain < -C.BACK_PASS_M and end_depth <= C.BACK_PASS_ZONE_M
            facing = self.local_vel(j, team)[0] < -C.FACING_OWN_GOAL_MS
            if trigger(back, False, facing):
                self.press_trigger(1 - team, "back_pass" if back else "facing_own_goal")

    def local_vel(self, j: int, team: int) -> np.ndarray:
        v: np.ndarray = self.vel[j] if self.right(team) else -self.vel[j]
        return v

    def press_trigger(self, team: int, kind: str) -> None:
        """`team` reads a cue to press (`tactics.pressing_trigger`); how often it reacts
        is its press intensity (a tactic, uncapped)."""
        presser = self.nearest(self.ball, team)
        if self.dist(presser, self.ball) > C.TRIGGER_RANGE_M:
            return
        if self.rng.random() >= self.tmods[team].press_intensity:
            return
        self.s.trigger_until[team] = self.k + round(C.TRIGGER_S / C.DT)
        self.emit("pressure", team, presser, self.pos[presser], extras={"trigger": kind})

    def team_phase(self, team: int) -> Phase:
        s = self.s
        depth = float(self.local(self.ball, team)[0])
        if s.poss_team == team:
            return "counter" if self.k < s.won_k + round(C.COUNTER_S / C.DT) else "build_up"
        if (s.phase == "dead" and s.dead is not None and s.dead.restart in ("corner", "free_kick")
                and depth <= C.LOW_BLOCK_DEPTH_M):  # fmt: skip
            return "set_piece"
        intensity = self.tmods[team].press_intensity
        if self.k < s.trigger_until[team] or (
            depth >= C.HIGH_PRESS_DEPTH_M and intensity >= C.HIGH_PRESS_MIN_INTENSITY
        ):
            return "high_press"
        if depth < C.LOW_BLOCK_DEPTH_M or (
            intensity < C.DEEP_TEAM_INTENSITY and depth < C.DEEP_TEAM_LOW_BLOCK_M
        ):
            return "low_block"
        return "mid_block"

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
        if b[2] > (C.HEADER_HEIGHT_M if f.header else C.CONTROL_HEIGHT_M):
            return
        # The ball travels up to 2-3 m per tick: reach is measured to its path since the
        # last tick, and it is controlled at the nearest point of that path.
        prev = f.traj.positions_at(max(t - C.DT, 0.0))[:2]
        near, d = self._reach(prev, b[:2])
        if f.collector is not None and self.k >= f.collect_from_k:
            j = f.collector
            if d[j] <= (C.HEADER_REACH_M if f.header else C.CONTROL_RANGE_M):
                self.control(j, f, near[j])
                return
        d = np.where(self.active, d, np.inf)
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
            tgt = self.pos.copy()  # players sent off keep their (off-pitch) spot
            for team in (0, 1):
                slots = [j for j in self.members(team) if self.active[j]]
                phase = self.team_phase(team)
                a = formation_shape(self.formations[team], phase, len(slots))
                df = np.array([line == "DF" for line in shape_lines(self.formations[team],
                                                                    len(slots))])  # fmt: skip
                b = self.local(self.ball, team)
                d = a[:, 0] + C.BLOCK_SHIFT * (b[0] - CENTRE[0])
                w = a[:, 1] + C.BALL_SIDE_SHIFT * (b[1] - CENTRE[1])
                if s.poss_team == team:
                    d[0] = min(a[0, 0], max(b[0] - 20.0, 4.0))
                    w[0] = CENTRE[1]
                    opp = self.pos[[j for j in self.members(1 - team) if self.active[j]]]
                    line = offside_line(opp, self.ball, self.right(team))
                    onside = float(self.local(np.array([line, 0.0]), team)[0]) - C.ONSIDE_MARGIN_M
                    d[1:] = np.minimum(d[1:], onside)
                else:
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
                tgt[slots] = self.local(local, team)
        moved = np.hypot(*(tgt - self.spot).T) > C.SHAPE_DEADBAND_M
        self.spot[moved] = tgt[moved]
        tgt = self.spot.copy()
        dist = np.hypot(*(tgt - self.pos).T)
        urg = np.clip(dist * C.SHAPE_URGENCY_PER_M, *C.SHAPE_URGENCY) * self.urgency_factor()
        if self.k < s.transition_until:
            urg[dist > C.TRANSITION_MIN_M] = C.TRANSITION_URGENCY
        return tgt, urg

    def urgency_factor(self) -> np.ndarray:
        """Off-ball effort: work rate (`offball_distance`), and tired players jog less."""
        work = np.array([m.offball_distance for m in self.pmods])
        factor: np.ndarray = work * (
            C.TIRED_URGENCY + (1.0 - C.TIRED_URGENCY) * np.clip(self.energy, 0, 1)
        )
        return factor

    def defend_ball(self, tgt: np.ndarray, urg: np.ndarray, team: int) -> None:
        """Out of possession: the nearest player presses (or contains), the next covers."""
        lo = 11 * team + 1
        d = np.hypot(*(self.pos[lo : lo + 10] - self.ball).T)
        order = lo + np.argsort(d)
        b = self.local(self.ball, team)
        own_goal = np.array([0.0, CENTRE[1]])
        intensity = self.tmods[team].press_intensity
        presser, cover = int(order[0]), int(order[1])
        if self.k < self.s.trigger_until[team]:
            # A triggered press: the nearest two close the ball down at full speed.
            p = b + PRESS_GOAL_SIDE_M * _unit(own_goal - b)
            tgt[presser], urg[presser] = self.local(_clamp(p, 0.5), team), 1.0
            q = b + 2.5 * _unit(own_goal - b)
            tgt[cover], urg[cover] = self.local(_clamp(q, 0.5), team), C.TRIGGER_COVER_URGENCY
            return
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
        if b[0] >= C.FINAL_THIRD_M:
            self.box_runs(tgt, urg, team, [carrier, runner, *cands[:0]])
        if runner is None or b[0] < C.RUN_BALL_DEPTH_M:
            return
        opp = self.pos[self.on(1 - team)]
        line = offside_line(opp, self.ball, self.right(team))
        line_local = float(self.local(np.array([line, 0.0]), team)[0])
        here = self.local(self.pos[runner], team)
        running = s.run_start_k is not None and s.run_start_k <= self.k < s.run_end_k
        depth = line_local + RUN_DEPTH_M if running else line_local - RUN_HOVER_M
        tgt[runner] = self.local(_clamp(np.array([depth, here[1]]), 0.5), team)
        urg[runner] = 1.0 if running else RUN_WAIT_URGENCY

    def mark_runner(self, tgt: np.ndarray, urg: np.ndarray, team: int) -> None:
        """Out of possession near its own goal, the defender nearest the opponents' runner
        stays goal-side of him."""
        runner = self.s.runner
        if runner is None or self.local(self.ball, team)[0] > C.MARK_RUNNER_ZONE_M:
            return
        defenders = [j for j in self.on(team) if self.is_df[j] and urg[j] < C.SUPPORT_URGENCY]
        if not defenders:
            return
        marker = min(defenders, key=lambda j: self.dist(j, self.pos[runner]))
        opp = self.local(self.pos[runner], team)
        p = opp + C.MARK_GOAL_SIDE_M * _unit(np.array([0.0, CENTRE[1]]) - opp)
        tgt[marker], urg[marker] = self.local(_clamp(p, 0.5), team), C.SUPPORT_URGENCY

    def box_runs(self, tgt: np.ndarray, urg: np.ndarray, team: int, busy: list[int | None]) -> None:
        """With the ball in the final third, the two nearest midfielders or forwards (not
        the carrier, runner, or supports) arrive in the box, staying onside."""
        opp = self.pos[self.on(1 - team)]
        line = offside_line(opp, self.ball, self.right(team))
        onside = float(self.local(np.array([line, 0.0]), team)[0]) - C.ONSIDE_MARGIN_M
        free = [j for j in self.on(team) if j % 11 != 0 and not self.is_df[j] and j not in busy
                and urg[j] < C.SUPPORT_URGENCY]  # fmt: skip
        free.sort(key=lambda j: -float(self.local(self.pos[j], team)[0]))
        for j, spot in zip(free[: C.BOX_RUNNERS], C.BOX_RUN_SPOTS, strict=False):
            p = np.array([min(spot[0], onside), spot[1]])
            tgt[j], urg[j] = self.local(p, team), C.BOX_RUN_URGENCY

    def targets(self) -> tuple[np.ndarray, np.ndarray]:
        s = self.s
        tgt, urg = self.shape()
        if s.phase == "held" and s.owner is not None:
            i = s.owner
            team = int(self.team_of[i])
            self.attack_ball(tgt, urg, team, i)
            self.defend_ball(tgt, urg, 1 - team)
            self.mark_runner(tgt, urg, 1 - team)
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
            dead = s.dead
            team = int(self.team_of[dead.taker])
            if dead.restart == "corner":
                for j, spot in zip(
                    self.corner_attackers(team, dead.taker), C.CORNER_SPOTS, strict=False
                ):
                    tgt[j], urg[j] = self.local(np.array(spot), team), C.TAKER_URGENCY
            elif dead.restart == "penalty":
                for j in self.on(0) + self.on(1):
                    local = self.local(tgt[j], team)
                    if j != dead.taker and j % 11 != 0 and in_box(local):
                        edge = np.array([PITCH_LENGTH - BOX_DEPTH_M - 1.0, local[1]])
                        tgt[j] = self.local(edge, team)
                gk = 11 * (1 - team)
                tgt[gk] = self.local(np.array([PITCH_LENGTH - 0.3, CENTRE[1]]), team)
            tgt[dead.taker], urg[dead.taker] = dead.spot, C.TAKER_URGENCY
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

    def tally(self) -> None:
        """Add this tick to each player's motion: what the frame records now."""
        on = self.active
        step = np.hypot(*(self.pos - self._last).T)
        self._dist += np.where(on & np.isfinite(step), step, 0.0)
        self._last = np.where(on[:, None], self.pos, np.nan)
        speed = np.hypot(*self.vel.T)
        self._top = np.where(on, np.maximum(self._top, speed), self._top)
        fast = on & (speed > SPRINT_SPEED_MS)
        ended = ~fast & (self._run >= SPRINT_TICKS)
        self._sprints += ended
        self._run = np.where(fast, self._run + 1, 0)
        self._ticks += on

    def flush_motion(self, slot: int) -> None:
        """Bank the slot's tally under its current player (substitution, red, half end)."""
        m = self.motion.setdefault(self.ids[slot], Motion())
        m.distance_m += float(self._dist[slot])
        m.top_speed_ms = max(m.top_speed_ms, float(self._top[slot]))
        m.sprints += int(self._sprints[slot]) + int(self._run[slot] >= SPRINT_TICKS)
        m.minutes += float(self._ticks[slot]) * C.DT / 60.0
        self._dist[slot] = self._top[slot] = 0.0
        self._sprints[slot] = self._ticks[slot] = self._run[slot] = 0
        self._last[slot] = np.nan

    def setup_period(self, period: Literal[1, 2], added_s: float) -> None:
        self.period = period
        self.n_ticks = round((C.HALF_S + added_s) / C.DT)
        self.s = _State()
        self.events = []
        self.history.clear()
        self.pos = self.kickoff_shape()
        for j in self.sent_off:
            self.pos[j] = C.OFF_PITCH
        self.spot = self.pos.copy()
        self.record_roster()
        self.vel = np.zeros((22, 2))
        if period == 2:
            self.energy = np.minimum(self.energy + C.HALF_TIME_RECOVERY, 1.0)
        kick_team = 0 if period == 1 else 1
        taker = max(self.on(kick_team), key=lambda j: float(self.anchors[j, 0]))
        self.pos[taker] = CENTRE
        self.k = 0
        self.start_dead(CENTRE.copy(), taker, "kickoff", pause_s=0.0, kickoff=True)

    def tick(self) -> None:
        self.match_flow()
        self.logic()
        self.update_ball()
        self.history.append((self.pos.copy(), self.vel.copy()))
        self.tally()
        if self.tracking:
            self.rec_pos.append(self.pos.copy())
            self.rec_vel.append(self.vel.copy())
            self.rec_ball.append((float(self.ball[0]), float(self.ball[1]), self.ball_z))
            self.rec_roster.append(len(self.rosters) - 1)
        self.move()
        self.k += 1

    def finish_period(self) -> None:
        s = self.s
        for slot in range(22):
            if self.active[slot]:
                self.flush_motion(slot)
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
                                        self.rec_vel, self.rec_ball, self.rosters,
                                        self.rec_roster)  # fmt: skip
            self.rec_pos, self.rec_vel, self.rec_ball, self.rec_roster = [], [], [], []

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


def simulate_with_motion(
    meta: MatchMeta,
    tracking: bool = True,
    profiles: Profiles | None = None,
    scenario: Scenario | None = None,
) -> tuple[MatchData, dict[str, Motion]]:
    """A match plus each player's `Motion` (exact without frames: for season history)."""
    eng = Coupled(meta, tracking, profiles, scenario=scenario)
    data = eng.run()
    return data, eng.motion


def simulate_coupled(
    meta: MatchMeta,
    tracking: bool = True,
    profiles: Profiles | None = None,
    scenario: Scenario | None = None,
) -> MatchData:
    """Same meta (and seed) gives identical events and frames.

    `tracking=False` returns no frames; events are unchanged (recording uses no RNG).
    """
    return Coupled(meta, tracking, profiles, scenario=scenario).run()
