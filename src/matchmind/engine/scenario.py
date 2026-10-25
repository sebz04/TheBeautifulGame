"""Scenarios: a fixture plus storyline beats that bias the match at given minutes.

Beats never teleport the state. A `red_card` makes the team's next foul a sending-off
(and raises its tackle rate until then); `goal` lifts the team's chance quality for a
window; `sub` brings on the best bench player for the most tired one of a position;
`tactic_change` and `press_intensity` change team tactics; `fatigue_spike` drains the
team's energy (or one player's, with `params.slot`). While a beat's window is open, the
targeted team's modifiers use the storyline cap (20%) instead of the subtle one (6%).
Files are TOML (`load_scenario`).
"""

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from matchmind.engine.lineup import match_meta
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import League
from matchmind.schemas import MatchMeta

SCENARIO_DIR = Path(__file__).resolve().parents[3] / "scenarios"
BeatKind = Literal["red_card", "goal", "sub", "tactic_change", "press_intensity", "fatigue_spike"]
TACTIC_KEYS = frozenset({"press_intensity", "line_height", "tempo", "width", "directness"})


class Beat(BaseModel):
    minute: float = Field(ge=0.0, le=90.0)
    kind: BeatKind
    team: Literal["home", "away"]
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_params(self) -> "Beat":
        slot = self.params.get("slot")
        if self.kind == "fatigue_spike" and slot is not None and not 1 <= int(slot) <= 10:
            raise ValueError("fatigue_spike slot must be an outfield slot (1-10)")
        if self.kind in ("tactic_change", "press_intensity"):
            keys = set(self.params) if self.kind == "tactic_change" else {"press_intensity"}
            values = self.params if self.kind == "tactic_change" else {
                "press_intensity": self.params.get("value", 1.0)}  # fmt: skip
            if not keys <= TACTIC_KEYS:
                raise ValueError(f"unknown tactic keys: {sorted(keys - TACTIC_KEYS)}")
            if not all(0.0 <= float(values[k]) <= 1.0 for k in keys):
                raise ValueError("tactic values must be in [0, 1]")
        return self


class Scenario(BaseModel):
    scenario_id: str
    title: str
    home_club_id: str
    away_club_id: str
    seed: int
    beats: list[Beat] = Field(default_factory=list)

    @field_validator("beats")
    @classmethod
    def _sorted(cls, beats: list[Beat]) -> list[Beat]:
        return sorted(beats, key=lambda b: b.minute)


def load_scenario(path: Path) -> Scenario:
    with Path(path).open("rb") as f:
        return Scenario.model_validate(tomllib.load(f))


def scenario_meta(league: League, scenario: Scenario, fixture_seed: int = 2026) -> MatchMeta:
    """Match setup for the scenario's fixture (home vs away in the league calendar)."""
    fixture = next(
        f for f in build_fixtures(league, seed=fixture_seed)
        if (f.home_id, f.away_id) == (scenario.home_club_id, scenario.away_club_id)
    )  # fmt: skip
    return match_meta(league, fixture, seed=scenario.seed, scenario_id=scenario.scenario_id)
