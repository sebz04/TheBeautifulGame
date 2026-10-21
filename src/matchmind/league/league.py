"""Build the league: clubs, 20-player squads, and the hidden latent factors behind them.

Every visible attribute (summary ratings here, full profiles in `profiles.py`) is derived
from a few latent factors per player, so attributes correlate the way they do in real life.
"""

import math
from typing import Literal

from pydantic import BaseModel

from matchmind.league.clubs import CLUBS
from matchmind.league.dist import rating, stream, truncated_normal
from matchmind.league.names import draw_nationality, make_name
from matchmind.schemas import Club, Player

Slot = Literal["GK", "CB", "FB", "DM", "CM", "AM", "W", "ST"]

# 2 GK, 7 DF (4 CB + 3 FB), 7 MF (2 DM + 3 CM + 2 AM), 4 FW (2 W + 2 ST)
_SLOT_COUNTS: list[tuple[Slot, int]] = [
    ("GK", 2), ("CB", 4), ("FB", 3), ("DM", 2), ("CM", 3), ("AM", 2), ("W", 2), ("ST", 2),
]  # fmt: skip
SQUAD_SLOTS: list[Slot] = [slot for slot, n in _SLOT_COUNTS for _ in range(n)]
SLOT_POSITION: dict[Slot, Literal["GK", "DF", "MF", "FW"]] = {
    "GK": "GK", "CB": "DF", "FB": "DF", "DM": "MF", "CM": "MF", "AM": "MF", "W": "FW", "ST": "FW",
}  # fmt: skip
FORMATIONS = ["4-3-3", "4-2-3-1", "4-4-2", "3-5-2"]
FORMATION_WEIGHTS = [0.35, 0.30, 0.25, 0.10]

CLUB_STRENGTH_SD = 0.45
PLAYER_QUALITY_SD = 0.55
QUALITY_SD = math.sqrt(CLUB_STRENGTH_SD**2 + PLAYER_QUALITY_SD**2)
AGE_MEAN, AGE_SD = 26.5, 4.2


class PlayerLatent(BaseModel):
    """Hidden factors (each ~N(0, 1) except age); never shown directly in the product."""

    slot: Slot
    nationality: str
    quality: float  # standardized: club strength + individual quality
    temperament: float  # high = fiery
    athleticism: float
    mentality: float  # professionalism, focus
    age: float
    debut_age: float

    @property
    def experience(self) -> float:
        """Standardized age, used as the experience factor."""
        return (self.age - AGE_MEAN) / AGE_SD

    @property
    def years_pro(self) -> int:
        return max(0, int(self.age - self.debut_age))


class League(BaseModel):
    clubs: list[Club]
    squads: dict[str, list[Player]]
    latents: dict[str, PlayerLatent]
    strength: dict[str, float]  # standardized club strength


def _age_decline(age: float) -> float:
    return max(0.0, age - 29.0) * 0.18


def _summary_ratings(lat: PlayerLatent) -> tuple[float, float, float]:
    pace = rating(0.85 * lat.athleticism + 0.25 * lat.quality - _age_decline(lat.age) + 0.2)
    skill = rating(0.85 * lat.quality + 0.25 * lat.mentality + 0.15 * min(lat.experience, 1.5))
    stamina = rating(0.7 * lat.athleticism + 0.4 * lat.mentality - 0.5 * _age_decline(lat.age))
    return pace, skill, stamina


def build_league(seed: int = 2026) -> League:
    clubs: list[Club] = []
    squads: dict[str, list[Player]] = {}
    latents: dict[str, PlayerLatent] = {}
    strength: dict[str, float] = {}
    rng = stream(seed, "league")

    for seed_club in CLUBS:
        formation = str(rng.choice(FORMATIONS, p=FORMATION_WEIGHTS))
        clubs.append(
            Club(
                club_id=seed_club.club_id,
                name=seed_club.name,
                short=seed_club.short,
                primary_color=seed_club.primary_color,
                secondary_color=seed_club.secondary_color,
                formation=formation,
            )
        )
        club_strength = float(rng.normal(0.0, CLUB_STRENGTH_SD))
        strength[seed_club.club_id] = club_strength / CLUB_STRENGTH_SD

        backup_gk = int(rng.choice([13, 25, 31]))
        outfield = [
            int(n) for n in rng.choice(range(2, 34), size=18, replace=False) if n != backup_gk
        ]
        while len(outfield) < 18:
            extra = int(rng.integers(35, 99))
            if extra not in outfield and extra != backup_gk:
                outfield.append(extra)
        numbers = [1, backup_gk] + outfield[:18]

        squad: list[Player] = []
        for idx, slot in enumerate(SQUAD_SLOTS):
            nationality = draw_nationality(rng)
            age_mean = AGE_MEAN + (1.5 if slot == "GK" else 0.0)
            quality = (club_strength + float(rng.normal(0.0, PLAYER_QUALITY_SD))) / QUALITY_SD
            lat = PlayerLatent(
                slot=slot,
                nationality=nationality,
                quality=round(quality, 4),
                temperament=round(float(rng.standard_normal()), 4),
                athleticism=round(float(rng.standard_normal()), 4),
                mentality=round(float(rng.standard_normal()), 4),
                age=round(truncated_normal(rng, age_mean, AGE_SD, 17.0, 37.0), 1),
                debut_age=round(truncated_normal(rng, 19.0, 1.5, 16.0, 23.0), 1),
            )
            if lat.debut_age > lat.age:
                lat = lat.model_copy(update={"debut_age": lat.age})
            pace, skill, stamina = _summary_ratings(lat)
            player_id = f"{seed_club.short.lower()}-{idx + 1:02d}"
            squad.append(
                Player(
                    player_id=player_id,
                    name=make_name(rng, nationality),
                    club_id=seed_club.club_id,
                    number=numbers[idx],
                    position=SLOT_POSITION[slot],
                    pace=pace,
                    skill=skill,
                    stamina=stamina,
                )
            )
            latents[player_id] = lat
        squads[seed_club.club_id] = squad

    return League(clubs=clubs, squads=squads, latents=latents, strength=strength)
