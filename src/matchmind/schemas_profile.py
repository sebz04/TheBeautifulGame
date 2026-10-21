"""Player and club profiles: the attributes behind behavior (engine) and context (narratives).

Ratings are in [0, 1]; money is in USD millions (`*_m`). Flags are computed from the
underlying fields so they can never disagree with them.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, computed_field

from matchmind.league.clubs import derby_rival

Rating = Annotated[float, Field(ge=0.0, le=1.0)]
Position = Literal["GK", "DF", "MF", "FW"]
Role = Literal[
    "sweeper_keeper", "shot_stopper",
    "ball_playing_cb", "stopper", "fullback", "wingback", "inverted_fullback",
    "anchor", "deep_playmaker", "box_to_box", "playmaker", "advanced_playmaker", "shadow_striker",
    "winger", "inside_forward", "target_man", "poacher", "false_nine", "pressing_forward",
]  # fmt: skip
SEASON_YEAR = 2026


class Personality(BaseModel):
    composure: Rating
    aggression: Rating
    confidence: Rating
    leadership: Rating
    consistency: Rating


class Style(BaseModel):
    position: Position
    secondary_position: Position | None
    role: Role
    work_rate: Rating
    tactical_discipline: Rating
    risk_tolerance: Rating


class Technical(BaseModel):
    passing: Rating
    first_touch: Rating
    dribbling: Rating
    finishing: Rating
    crossing: Rating
    tackling: Rating
    aerial: Rating
    shot_stopping: Rating
    distribution: Rating


class Origin(BaseModel):
    """How and when the player joined their current club, and their record there."""

    kind: Literal["academy", "signed", "loan", "free"]
    joined_year: int
    signed_from: str | None  # in-league club_id, "ext:<ISO3>" for abroad, None for academy
    fee_m: float = Field(ge=0.0)
    club_apps: int = Field(ge=0)
    club_goals: int = Field(ge=0)


class Career(BaseModel):
    nationality: str
    birth_year: int
    years_pro: int = Field(ge=0)
    stage: Literal["rookie", "prime", "veteran"]
    caps: int = Field(ge=0)
    contract_until: int
    market_value_m: float = Field(gt=0.0)
    contract_negotiations: Literal["none", "in_talks", "stalled", "extended"]
    transfer_interest: list[str]
    retirement_risk: Rating
    previous_league_clubs: list[str] = Field(default_factory=list)


class Discipline(BaseModel):
    career_yellows: int = Field(ge=0)
    career_reds: int = Field(ge=0)
    season_yellows: int = Field(default=0, ge=0)
    suspended_until_round: int | None = None


class Status(BaseModel):
    injury: Literal["fit", "returning", "doubtful"]
    games_missed: int = Field(ge=0)
    captain: bool
    preferred_foot: Literal["right", "left", "both"]
    height_cm: int


class PlayerProfile(BaseModel):
    player_id: str
    club_id: str
    personality: Personality
    style: Style
    technical: Technical
    career: Career
    discipline: Discipline
    status: Status
    origin: Origin | None = None  # filled by build_profiles (TASK-3.4)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_academy(self) -> bool:
        return self.origin is not None and self.origin.kind == "academy"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_new_signing(self) -> bool:
        return (
            self.origin is not None
            and self.origin.kind != "academy"
            and self.origin.joined_year == SEASON_YEAR
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_former_rival(self) -> bool:
        rival = derby_rival(self.club_id)
        return rival is not None and rival in self.career.previous_league_clubs

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_returning_from_injury(self) -> bool:
        return self.status.injury == "returning"
