"""Shared data models: the single source of truth for every module and API payload.

Units: metres on a 105 x 68 m pitch (origin bottom-left), seconds since kickoff
of the current period, speeds in m/s.
"""

import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

EventType = Literal[
    "kickoff",
    "pass",
    "carry",
    "shot",
    "tackle",
    "interception",
    "pressure",
    "foul",
    "card",
    "sub",
    "goal",
    "out",
    "save",
    "clearance",
    "offside",
]
Period = Literal[1, 2]
Persona = Literal["analyst", "casual", "club_fan", "player_focus"]
Lang = Literal["en", "es", "pt", "fr", "ar"]
Level = Literal["game", "team", "player"]
MomentKind = Literal[
    "momentum_swing",
    "pressing_collapse",
    "formation_shift",
    "big_chance",
    "goal",
    "red_card",
    "sprint_alert",
    "offside_trap",
    "corner_pressure",
    "player_deviation",
]
CueKind = Literal[
    "name_tag", "speed_alert", "distance_alert", "stat_card", "freeze_frame", "insight", "narrative"
]
Rating = float  # attribute in [0, 1]


def trusted[M: BaseModel](cls: type[M], data: dict[str, Any]) -> M:
    """Build a model without validation, about 3x cheaper than `model_construct`.

    Only for data our own code produced with the right types (engine frames, our own
    Parquet files); `data` must hold every field. Equal to the validated model.
    """
    obj = cls.__new__(cls)
    object.__setattr__(obj, "__dict__", data)
    object.__setattr__(obj, "__pydantic_fields_set__", set(data))
    object.__setattr__(obj, "__pydantic_extra__", None)
    object.__setattr__(obj, "__pydantic_private__", None)
    return obj


_EVENT_ID = re.compile(r"^(?P<match>.+)-e\d{5}$")


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    match_id: str
    period: Period
    t: float
    type: EventType
    team_id: str
    player_id: str | None
    x: float
    y: float
    end_x: float | None
    end_y: float | None
    outcome: bool | None
    receiver_id: str | None
    ball_speed_ms: float | None
    extras: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _event_id_matches_match(self) -> Self:
        m = _EVENT_ID.match(self.event_id)
        if m is None or m.group("match") != self.match_id:
            raise ValueError(f"event_id must be '{self.match_id}-eNNNNN', got {self.event_id!r}")
        return self


class PlayerPos(BaseModel):
    model_config = ConfigDict(frozen=True)

    player_id: str
    team_id: str
    x: float
    y: float
    vx: float
    vy: float


class TrackingFrame(BaseModel):
    match_id: str
    frame: int
    period: Period
    t: float
    ball: tuple[float, float, float]
    players: list[PlayerPos]


class Player(BaseModel):
    player_id: str
    name: str
    club_id: str
    number: int = Field(ge=1, le=99)
    position: Literal["GK", "DF", "MF", "FW"]
    pace: Rating = Field(ge=0, le=1)
    skill: Rating = Field(ge=0, le=1)
    stamina: Rating = Field(ge=0, le=1)


class Club(BaseModel):
    club_id: str
    name: str
    short: str
    primary_color: str
    secondary_color: str
    formation: str


class MatchMeta(BaseModel):
    match_id: str
    seed: int
    home: Club
    away: Club
    home_squad: list[Player]
    away_squad: list[Player]
    scenario_id: str
    engine_version: str
    stadium: str
    kickoff_iso: str
    added_time_s: tuple[float, float]


class MatchData(BaseModel):
    meta: MatchMeta
    events: list[Event]
    frames: list[TrackingFrame]


class Moment(BaseModel):
    moment_id: str
    match_id: str
    period: Period
    t_start: float
    t_end: float
    kind: MomentKind
    level: Level
    team_id: str | None
    player_id: str | None
    trigger_metric: str
    trigger_value: float
    event_ids: list[str]


class Claim(BaseModel):
    """One checkable statement. `ref` is an event_id or 'metric:<name>@<t>'."""

    text: str
    metric: str
    value: float
    unit: str
    ref: str


class Insight(BaseModel):
    insight_id: str
    moment_id: str
    match_id: str
    level: Level
    headline: str
    why: str
    recommendation: str
    claims: list[Claim]
    event_ids: list[str]
    confidence: Literal["high", "medium", "low"]
    verified: bool
    source: Literal["agent", "template"]
    trace_id: str | None
    prompt_version: str


class PersonalizedText(BaseModel):
    """`club_id` is set for club_fan texts, `player_id` for player_focus texts."""

    insight_id: str
    persona: Persona
    lang: Lang
    headline: str
    body: str
    verified: bool
    club_id: str | None = None
    player_id: str | None = None


class Variant(BaseModel):
    persona: Persona
    club_id: str | None = None
    player_id: str | None = None


class OverlayCue(BaseModel):
    cue_id: str
    match_id: str
    period: Period
    t_in: float
    t_out: float
    kind: CueKind
    priority: int
    payload: dict[str, Any]


class MetricRow(BaseModel):
    """One materialized metric value at (period, t): a 30 s grid point or a moment's end."""

    match_id: str
    period: Period
    t: float
    scope: Literal["team", "player"]
    scope_id: str
    name: str
    value: float | None
    kind: Literal["grid", "moment"]


class AgentRun(BaseModel):
    run_id: str
    agent: str
    moment_id: str | None
    status: Literal["ok", "retry", "failed", "fallback"]
    attempts: int
    latency_ms: int
    trace_id: str | None
    error: str | None
