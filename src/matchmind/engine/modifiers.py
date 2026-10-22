"""Modifier layer: player and club profiles -> small, capped behavior multipliers.

Every effect is `1 + clip(effect, ±cap)` with `cap = SUBTLE_CAP` (6%) by default and
`STORYLINE_CAP` (20%) only while a scenario beat targets the player or team. Traits enter
as `dev(x) = clip((x - 0.5) / 0.25, -1, 1)`, so a typical trait moves behavior by a few
percent and only extremes reach the cap. Terms are weighted so their sum stays within
±1 before scaling, which keeps every input visible instead of saturating.
`to_extras()` lists effects above 0.01 for `Event.extras["mods"]`, so explanations can
cite real causes. Team tactics (`TeamMods.press_intensity`, ...) are settings, not
modifiers, and are not capped.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np
from pydantic import BaseModel

from matchmind.schemas_profile import ClubProfile, PlayerProfile

SUBTLE_CAP = 0.06
STORYLINE_CAP = 0.20
RECORD_THRESHOLD = 0.01
LATE_MINUTE = 75.0
CHASE_MINUTE = 60.0
CONGESTED_DAYS = 3


class MatchContext(BaseModel):
    minute: float = 0.0
    score_diff: int = 0  # own goals minus opponent goals
    is_home: bool = True
    energy: float = 1.0
    confidence: float = 0.5  # in-match state: up after successes, down after errors
    storyline: bool = False  # a scenario beat targets this player or team right now
    congestion_days: int = 7  # days since the previous match
    form: float = 0.0  # match-day form from `match_form`, in [-1, 1]


def dev(x: float) -> float:
    return float(np.clip((x - 0.5) / 0.25, -1.0, 1.0))


def _experience(years_pro: int) -> float:
    return float(np.clip((years_pro - 6) / 5, -1.0, 1.0))


@dataclass(frozen=True)
class _Mods:
    effects: dict[str, float] = field(default_factory=dict)

    def mult(self, name: str) -> float:
        return 1.0 + self.effects.get(name, 0.0)

    def to_extras(self, only: Iterable[str] | None = None) -> dict[str, float]:
        """Effects above the threshold, rounded; `only` limits them to the action's
        relevant modifiers (e.g. a tackle records tackle_rate, foul_rate, tackle_error)."""
        keep = None if only is None else set(only)
        rounded = {k: round(v, 3) for k, v in sorted(self.effects.items())
                   if keep is None or k in keep}  # fmt: skip
        return {k: v for k, v in rounded.items() if abs(v) > RECORD_THRESHOLD}


@dataclass(frozen=True)
class PlayerMods(_Mods):
    @property
    def decision_temperature(self) -> float:
        return self.mult("decision_temperature")

    @property
    def tackle_rate(self) -> float:
        return self.mult("tackle_rate")

    @property
    def foul_rate(self) -> float:
        return self.mult("foul_rate")

    @property
    def press_urgency(self) -> float:
        return self.mult("press_urgency")

    @property
    def shot_rate(self) -> float:
        return self.mult("shot_rate")

    @property
    def teammate_composure(self) -> float:
        return self.mult("teammate_composure")

    @property
    def form(self) -> float:
        return self.mult("form")

    @property
    def offball_distance(self) -> float:
        return self.mult("offball_distance")

    @property
    def energy_drain(self) -> float:
        return self.mult("energy_drain")

    @property
    def anchor_tightness(self) -> float:
        return self.mult("anchor_tightness")

    @property
    def risk_weight(self) -> float:
        return self.mult("risk_weight")

    @property
    def run_timing_sd(self) -> float:
        return self.mult("run_timing_sd")

    @property
    def start_energy(self) -> float:
        return self.mult("start_energy")

    @property
    def pass_error(self) -> float:
        return self.mult("pass_error")

    @property
    def touch_error(self) -> float:
        return self.mult("touch_error")

    @property
    def dribble_error(self) -> float:
        return self.mult("dribble_error")

    @property
    def shot_error(self) -> float:
        return self.mult("shot_error")

    @property
    def cross_error(self) -> float:
        return self.mult("cross_error")

    @property
    def tackle_error(self) -> float:
        return self.mult("tackle_error")

    @property
    def aerial_error(self) -> float:
        return self.mult("aerial_error")

    @property
    def gk_error(self) -> float:
        return self.mult("gk_error")

    @property
    def distribution_error(self) -> float:
        return self.mult("distribution_error")


@dataclass(frozen=True)
class TeamMods(_Mods):
    """Tactical settings (uncapped, from the club's identity) plus capped modifiers."""

    press_intensity: float = 0.5
    line_height: float = 0.5
    tempo: float = 0.5
    width: float = 0.5
    directness: float = 0.5

    @property
    def chase_urgency(self) -> float:
        return self.mult("chase_urgency")

    @property
    def home_boost(self) -> float:
        return self.mult("home_boost")


@dataclass(frozen=True)
class PairMods:
    completion: float
    run_early: float


_TECHNICAL_ERRORS = {
    "pass_error": "passing",
    "touch_error": "first_touch",
    "dribble_error": "dribbling",
    "shot_error": "finishing",
    "cross_error": "crossing",
    "tackle_error": "tackling",
    "aerial_error": "aerial",
    "gk_error": "shot_stopping",
    "distribution_error": "distribution",
}


def _cap(ctx: MatchContext) -> float:
    return STORYLINE_CAP if ctx.storyline else SUBTLE_CAP


def _home_term(club: ClubProfile, ctx: MatchContext) -> float:
    """Home crowd: never negative, up to +0.15 on a trait for the strongest home grounds."""
    return max(0.0, club.home_advantage - 0.5) * 0.3 if ctx.is_home else 0.0


class Modifiers:
    @staticmethod
    def for_player(profile: PlayerProfile, club: ClubProfile, ctx: MatchContext) -> PlayerMods:
        cap = _cap(ctx)
        per, sty, tec = profile.personality, profile.style, profile.technical
        home = _home_term(club, ctx)
        late_close = ctx.minute >= LATE_MINUTE and abs(ctx.score_diff) <= 1
        pressure = 1.0 if late_close else 0.5
        confidence = 0.5 * per.confidence + 0.5 * ctx.confidence + home
        timing = (dev(sty.tactical_discipline) + dev(per.composure)
                  + _experience(profile.career.years_pro)) / 3  # fmt: skip
        start = -(1.0 if profile.status.injury == "returning" else
                  0.5 if profile.status.injury == "doubtful" else 0.0)  # fmt: skip
        start -= 0.5 if ctx.congestion_days <= CONGESTED_DAYS else 0.0

        raw = {
            "decision_temperature": -dev(per.composure + home) * pressure,
            "tackle_rate": dev(per.aggression),
            "foul_rate": dev(per.aggression),
            "press_urgency": dev(per.aggression),
            "shot_rate": dev(confidence),
            "teammate_composure": dev(per.leadership),
            "form": float(np.clip(ctx.form, -1.0, 1.0)),
            "offball_distance": dev(sty.work_rate),
            "energy_drain": dev(sty.work_rate),
            "anchor_tightness": dev(sty.tactical_discipline),
            "risk_weight": dev(sty.risk_tolerance),
            "run_timing_sd": -0.5 * timing + 0.5 * (1.0 - min(max(ctx.energy, 0.0), 1.0)),
            "start_energy": start,
        }
        for name, rating in _TECHNICAL_ERRORS.items():
            raw[name] = -dev(getattr(tec, rating))
        effects = {k: float(np.clip(v * cap, -cap, cap)) for k, v in raw.items()}
        return PlayerMods(effects={k: v for k, v in effects.items() if v != 0.0})

    @staticmethod
    def for_team(club: ClubProfile, ctx: MatchContext) -> TeamMods:
        cap = _cap(ctx)
        tactic = club.tactical_identity
        raw: dict[str, float] = {}
        if ctx.score_diff < 0 and ctx.minute >= CHASE_MINUTE:
            raw["chase_urgency"] = 0.5 + 0.5 * (1.0 - club.management.job_security)
        if ctx.is_home:
            raw["home_boost"] = dev(club.home_advantage)
        effects = {k: float(np.clip(v * cap, -cap, cap)) for k, v in raw.items()}
        return TeamMods(
            effects={k: v for k, v in effects.items() if v != 0.0},
            press_intensity=tactic.press_intensity,
            line_height=tactic.line_height,
            tempo=tactic.tempo,
            width=tactic.width,
            directness=tactic.directness,
        )


def match_form(profile: PlayerProfile, rng: np.random.Generator) -> float:
    """Match-day form in [-1, 1]; inconsistent players swing more (`MatchContext.form`)."""
    sd = 0.25 + 0.75 * (1.0 - profile.personality.consistency)
    return float(np.clip(rng.normal(0.0, sd), -1.0, 1.0))


def pair_mods(chemistry: float, storyline: bool = False) -> PairMods:
    """Passing pair: completion and how early the receiver starts the run."""
    cap = STORYLINE_CAP if storyline else SUBTLE_CAP
    effect = float(np.clip(dev(chemistry) * cap, -cap, cap))
    return PairMods(completion=1.0 + effect, run_early=1.0 + effect)
