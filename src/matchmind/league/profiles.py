"""Generate player and club profiles from the league's latent factors.

Each attribute is `rating(combine(...))` of a few latent factors, so traits are
bell-shaped and correlated the way they are in real squads. Money is log-normal.
"""

import math

import numpy as np

from matchmind.league.clubs import CLUBS
from matchmind.league.dist import combine, log_normal_money, rating, stream
from matchmind.league.league import League, PlayerLatent, Slot
from matchmind.league.names import draw_nationality, language_of, make_name
from matchmind.schemas_profile import (
    SEASON_YEAR,
    Career,
    ClubProfile,
    Discipline,
    Management,
    ManagerStyle,
    Personality,
    PlayerProfile,
    Position,
    Role,
    Status,
    Style,
    TacticalIdentity,
    Technical,
)

_POS: dict[Slot, Position] = {
    "GK": "GK", "CB": "DF", "FB": "DF", "DM": "MF", "CM": "MF", "AM": "MF", "W": "FW", "ST": "FW",
}  # fmt: skip

# Position priors (shift of the standardized score) per technical skill.
_SLOT_ORDER: tuple[Slot, ...] = ("GK", "CB", "FB", "DM", "CM", "AM", "W", "ST")
_TECH_TABLE: dict[str, tuple[float, ...]] = {
    #               GK    CB    FB    DM    CM    AM    W     ST
    "passing":     (-0.6, -0.1, 0.1,  0.5,  0.6,  0.6,  0.1,  -0.2),
    "first_touch": (-0.8, -0.2, 0.1,  0.3,  0.4,  0.6,  0.5,  0.4),
    "dribbling":   (-1.5, -0.6, 0.2,  -0.1, 0.2,  0.7,  0.9,  0.4),
    "finishing":   (-2.5, -1.0, -0.6, -0.4, 0.0,  0.5,  0.5,  1.0),
    "crossing":    (-2.0, -0.8, 0.7,  -0.2, 0.1,  0.3,  0.8,  -0.3),
    "tackling":    (-2.0, 0.9,  0.6,  0.8,  0.3,  -0.4, -0.5, -0.8),
}  # fmt: skip
_TECH_MU: dict[str, dict[Slot, float]] = {
    skill: dict(zip(_SLOT_ORDER, row, strict=True)) for skill, row in _TECH_TABLE.items()
}
_HEIGHT: dict[Slot, tuple[float, float]] = {
    "GK": (190, 4.5), "CB": (187, 4.5), "FB": (179, 5), "DM": (182, 5),
    "CM": (179, 5.5), "AM": (175, 5.5), "W": (175, 5.5), "ST": (183, 6),
}  # fmt: skip
_AGGRESSION_MU: dict[Position, float] = {"GK": -0.6, "DF": 0.15, "MF": -0.05, "FW": -0.25}
_WORK_RATE_MU: dict[Position, float] = {"GK": -0.5, "DF": 0.0, "MF": 0.3, "FW": 0.0}
_RISK_MU: dict[Position, float] = {"GK": -0.8, "DF": -0.5, "MF": 0.0, "FW": 0.6}
_SECONDARY: dict[Slot, Position | None] = {
    "GK": None, "CB": None, "FB": "MF", "DM": "DF", "CM": None, "AM": "FW", "W": "MF", "ST": None,
}  # fmt: skip


def _r(
    rng: np.random.Generator, mu: float, terms: list[tuple[float, float]], noise: float
) -> float:
    return rating(combine(rng, mu, terms, noise))


def _personality(rng: np.random.Generator, lat: PlayerLatent, pos: Position) -> Personality:
    q, t, m, e = lat.quality, lat.temperament, lat.mentality, lat.experience
    return Personality(
        composure=_r(rng, 0.0, [(0.5, m), (0.35, q), (-0.35, t), (0.3, e)], 0.7),
        aggression=_r(rng, _AGGRESSION_MU[pos], [(0.8, t)], 0.6),
        confidence=_r(rng, 0.0, [(0.5, q), (0.3, m), (0.15, t)], 0.8),
        leadership=_r(rng, -0.1, [(0.45, m), (0.55, e), (0.25, q)], 0.6),
        consistency=_r(rng, 0.0, [(0.55, m), (0.3, e), (-0.2, t)], 0.7),
    )


def _technical(rng: np.random.Generator, lat: PlayerLatent, height_z: float) -> Technical:
    q, m, a = lat.quality, lat.mentality, lat.athleticism
    skills = {
        name: _r(
            rng, mu[lat.slot], [(0.85, q), (0.2, m), (0.25 if name == "dribbling" else 0.0, a)], 0.6
        )
        for name, mu in _TECH_MU.items()
    }
    aerial_mu = {"GK": 0.3, "CB": 0.8, "ST": 0.4}.get(lat.slot, -0.2)
    if lat.slot == "GK":
        shot_stopping = _r(rng, 0.6, [(0.9, q), (0.2, a)], 0.5)
        distribution = _r(rng, 0.2, [(0.7, q), (0.3, m)], 0.6)
    else:
        shot_stopping = _r(rng, -4.5, [(0.2, q)], 0.3)
        distribution = _r(rng, -3.0, [(0.3, q)], 0.4)
    return Technical(
        **skills,
        aerial=_r(rng, aerial_mu, [(0.5, height_z), (0.5, q), (0.3, a)], 0.6),
        shot_stopping=shot_stopping,
        distribution=distribution,
    )


def _role(
    rng: np.random.Generator, slot: Slot, tech: Technical, work_rate: float, height: int
) -> Role:
    def jitter() -> float:
        return float(rng.normal(0.0, 0.05))

    if slot == "GK":
        return "sweeper_keeper" if tech.distribution + jitter() > 0.55 else "shot_stopper"
    if slot == "CB":
        return "ball_playing_cb" if tech.passing + jitter() > 0.5 else "stopper"
    if slot == "FB":
        if work_rate > 0.6 and tech.crossing > 0.55:
            return "wingback"
        return "inverted_fullback" if tech.passing > tech.crossing + 0.05 else "fullback"
    if slot == "DM":
        return "deep_playmaker" if tech.passing + jitter() > 0.6 else "anchor"
    if slot == "CM":
        return "playmaker" if tech.passing > 0.6 and work_rate < 0.55 else "box_to_box"
    if slot == "AM":
        return (
            "shadow_striker" if tech.finishing + jitter() > tech.passing else "advanced_playmaker"
        )
    if slot == "W":
        return "inside_forward" if tech.finishing + jitter() > tech.crossing else "winger"
    if tech.aerial > 0.6 and height >= 186:
        return "target_man"
    if work_rate > 0.6:
        return "pressing_forward"
    if tech.passing > tech.finishing:
        return "false_nine"
    return "poacher"


def _market_value(rng: np.random.Generator, lat: PlayerLatent) -> float:
    age_term = 0.12 * max(0.0, 23.0 - lat.age) - 0.15 * max(0.0, lat.age - 30.0)
    log_value = math.log(4.0) + 1.1 * lat.quality + age_term + 0.45 * float(rng.standard_normal())
    return round(min(max(math.exp(log_value), 0.1), 180.0), 1)


def _career(rng: np.random.Generator, lat: PlayerLatent, club_id: str, league: League) -> Career:
    years_pro = lat.years_pro
    stage = "rookie" if years_pro <= 2 else "veteran" if years_pro >= 10 else "prime"
    capped = rng.random() < 1.0 / (1.0 + math.exp(-1.6 * (lat.quality - 0.6)))
    caps = int(rng.poisson(max(1, years_pro) * (2 + 4 * max(0.0, lat.quality)))) if capped else 0
    contract_until = SEASON_YEAR + 1 + int(rng.choice(5, p=[0.3, 0.25, 0.2, 0.15, 0.1]))
    if contract_until == SEASON_YEAR + 1:
        negotiations = str(rng.choice(["in_talks", "stalled", "none"], p=[0.45, 0.2, 0.35]))
    else:
        negotiations = str(rng.choice(["none", "extended"], p=[0.85, 0.15]))
    interest: list[str] = []
    if lat.quality > 1.0 and lat.age < 29:
        bigger = [c for c, s in league.strength.items() if c != club_id and s > 0.3]
        k = min(len(bigger), 1 + int(lat.quality > 1.6) + int(rng.random() < 0.3))
        interest = sorted(str(c) for c in rng.choice(bigger, size=k, replace=False))
    retirement = rating((lat.age - 33.0) * 1.1 + 0.4 * float(rng.standard_normal()))
    return Career(
        nationality=lat.nationality,
        birth_year=SEASON_YEAR - int(lat.age),
        years_pro=years_pro,
        stage=stage,
        caps=caps,
        contract_until=contract_until,
        market_value_m=_market_value(rng, lat),
        contract_negotiations=negotiations,
        transfer_interest=interest,
        retirement_risk=retirement,
    )


def _discipline(
    rng: np.random.Generator, lat: PlayerLatent, aggression: float, pos: Position
) -> Discipline:
    apps = lat.years_pro * float(rng.uniform(18, 32))
    base = {"GK": 0.01, "DF": 0.07, "MF": 0.06, "FW": 0.04}[pos]
    yellows = int(rng.poisson(apps * (base + 0.22 * aggression)))
    reds = int(rng.poisson(apps * (0.0005 + 0.008 * aggression**2)))
    return Discipline(career_yellows=yellows, career_reds=reds)


def build_player_profiles(league: League, seed: int) -> dict[str, PlayerProfile]:
    """Intrinsic player profiles. Origins and transfers are added by `build_profiles`."""
    rng = stream(seed, "profiles.players")
    profiles: dict[str, PlayerProfile] = {}
    for club_id, squad in league.squads.items():
        club_profiles: list[PlayerProfile] = []
        for player in squad:
            lat = league.latents[player.player_id]
            pos = _POS[lat.slot]
            h_mu, h_sd = _HEIGHT[lat.slot]
            height_z = float(rng.standard_normal())
            height = int(round(h_mu + h_sd * height_z))
            personality = _personality(rng, lat, pos)
            technical = _technical(rng, lat, height_z)
            work_rate = _r(
                rng, _WORK_RATE_MU[pos], [(0.45, lat.athleticism), (0.5, lat.mentality)], 0.7
            )
            style = Style(
                position=pos,
                secondary_position=_SECONDARY[lat.slot] if rng.random() < 0.3 else None,
                role=_role(rng, lat.slot, technical, work_rate, height),
                work_rate=work_rate,
                tactical_discipline=_r(
                    rng, 0.2 if pos == "DF" else 0.0,
                    [(0.5, lat.mentality), (-0.35, lat.temperament), (0.3, lat.experience)], 0.7,
                ),
                risk_tolerance=_r(
                    rng, _RISK_MU[pos],
                    [(0.45, lat.temperament), (0.3, lat.quality), (-0.25, lat.experience)], 0.7,
                ),
            )  # fmt: skip
            p_returning = 0.06 + (0.03 if lat.age > 31 else 0.0)
            u = rng.random()
            injury = (
                "returning" if u < p_returning else "doubtful" if u < p_returning + 0.04 else "fit"
            )
            games_missed = {
                "returning": int(rng.integers(2, 13)),
                "doubtful": int(rng.integers(0, 3)),
            }.get(injury, 0)
            foot_u = rng.random()
            status = Status(
                injury=injury,
                games_missed=games_missed,
                captain=False,
                preferred_foot="left" if foot_u < 0.22 else "both" if foot_u < 0.25 else "right",
                height_cm=height,
            )
            club_profiles.append(
                PlayerProfile(
                    player_id=player.player_id,
                    club_id=club_id,
                    personality=personality,
                    style=style,
                    technical=technical,
                    career=_career(rng, lat, club_id, league),
                    discipline=_discipline(rng, lat, personality.aggression, pos),
                    status=status,
                )
            )
        eligible = [
            p for p in club_profiles if league.latents[p.player_id].age >= 24
        ] or club_profiles
        captain = max(eligible, key=lambda p: p.personality.leadership)
        for prof in club_profiles:
            if prof.player_id == captain.player_id:
                prof = prof.model_copy(
                    update={"status": prof.status.model_copy(update={"captain": True})}
                )
            profiles[prof.player_id] = prof
    return profiles


# ---- Clubs -----------------------------------------------------------------------------

_STYLE_WEIGHTS: dict[str, tuple[float, float, float, float]] = {
    # possession, pressing, counter, pragmatic
    "title_contender": (0.40, 0.35, 0.10, 0.15),
    "mid_table": (0.25, 0.25, 0.25, 0.25),
    "relegation_fight": (0.05, 0.20, 0.35, 0.40),
    "promoted": (0.05, 0.20, 0.35, 0.40),
}
_STYLES: tuple[ManagerStyle, ...] = ("possession", "pressing", "counter", "pragmatic")
# Prior shifts per tactical dimension: press, line, tempo, width, directness
_STYLE_PRIORS: dict[ManagerStyle, tuple[float, float, float, float, float]] = {
    "pressing": (1.1, 0.9, 0.7, 0.2, 0.2),
    "possession": (0.5, 0.6, -0.5, 0.4, -1.1),
    "counter": (-0.8, -1.0, 0.6, 0.0, 1.1),
    "pragmatic": (0.0, -0.2, 0.0, 0.0, 0.0),
}


def _tactical_identity(rng: np.random.Generator, style: ManagerStyle) -> TacticalIdentity:
    press, line, tempo, width, direct = (
        rating(mu + 0.6 * float(rng.standard_normal())) for mu in _STYLE_PRIORS[style]
    )
    build_up = "short" if direct < 0.4 else "direct" if direct > 0.62 else "mixed"
    return TacticalIdentity(
        press_intensity=press, line_height=line, tempo=tempo, width=width, directness=direct,
        build_up=build_up,
    )  # fmt: skip


def build_club_profiles(league: League, seed: int) -> dict[str, ClubProfile]:
    rng = stream(seed, "profiles.clubs")
    ids = [c.club_id for c in league.clubs]
    by_strength = sorted(ids, key=lambda c: -league.strength[c])
    expected_rank = {c: i + 1 for i, c in enumerate(by_strength)}
    promoted = {str(c) for c in rng.choice(by_strength[-7:], size=3, replace=False)}
    survivors = [c for c in ids if c not in promoted]
    noisy = {c: league.strength[c] + 0.35 * float(rng.standard_normal()) for c in survivors}
    last_finish = {c: i + 1 for i, c in enumerate(sorted(survivors, key=lambda c: -noisy[c]))}
    contenders = set(by_strength[:4])
    strugglers = {c for c in by_strength[-8:] if c not in promoted}

    new_owners = {str(c) for c in rng.choice(ids, size=3, replace=False)}
    fan_pool = [c for c in by_strength[6:] if c not in new_owners]
    fan_owned = {str(c) for c in rng.choice(fan_pool, size=2, replace=False)}

    capacities = {s.club_id: s.capacity for s in CLUBS}
    cap_mean = float(np.mean(list(capacities.values())))
    cap_sd = float(np.std(list(capacities.values())))

    profiles: dict[str, ClubProfile] = {}
    for club_id in ids:
        z = league.strength[club_id]
        status = (
            "promoted" if club_id in promoted
            else "title_contender" if club_id in contenders
            else "relegation_fight" if club_id in strugglers
            else "mid_table"
        )  # fmt: skip
        weights = np.array(_STYLE_WEIGHTS[status])
        style: ManagerStyle = _STYLES[int(rng.choice(4, p=weights / weights.sum()))]
        tenure = round(min(max(float(rng.exponential(2.2)), 0.2), 12.0), 1)
        finish = last_finish.get(club_id)
        over_performance = ((expected_rank[club_id] if finish else 18) - (finish or 18)) / 4.0
        job_security = rating(
            0.5 * math.log(tenure) + 0.7 * over_performance + 0.5 * float(rng.standard_normal())
        )
        manager = Management(
            manager_name=make_name(rng, draw_nationality(rng)),
            manager_style=style,
            manager_tenure_years=tenure,
            job_security=job_security,
        )
        if club_id in fan_owned:
            ownership, owner_since, culture = (
                "fan_owned",
                int(rng.integers(2000, 2016)),
                "fan_owned",
            )
        elif club_id in new_owners:
            ownership, owner_since = "new_owner", int(rng.choice([2025, 2026]))
            culture = "win_now" if rng.random() < 0.7 else "academy_first"
        else:
            ownership, owner_since = "long_standing", int(rng.integers(1955, 2019))
            options, p = {
                "title_contender": (["win_now", "academy_first", "underdog"], [0.65, 0.3, 0.05]),
                "mid_table": (["academy_first", "win_now", "underdog"], [0.45, 0.3, 0.25]),
            }.get(status, (["underdog", "academy_first", "win_now"], [0.6, 0.3, 0.1]))
            culture = str(rng.choice(options, p=p))
        budget = log_normal_money(rng, 35.0, 0.6 * z, 0.35)
        if ownership == "new_owner":
            budget = round(budget * 2.5, 1)
        elif status == "promoted":
            budget = round(budget * 0.6, 1)
        cap_z = (capacities[club_id] - cap_mean) / cap_sd
        profiles[club_id] = ClubProfile(
            club_id=club_id,
            tactical_identity=_tactical_identity(rng, style),
            management=manager,
            culture=culture,
            ownership=ownership,
            owner_since=owner_since,
            transfer_budget_m=max(budget, 1.0),
            wage_bill_m=log_normal_money(rng, 70.0, 0.55 * z, 0.2),
            last_finish=finish,
            status=status,
            home_advantage=rating(
                0.6 * cap_z
                + (0.4 if ownership == "fan_owned" else 0.0)
                + 0.7 * float(rng.standard_normal())
            ),
        )
    return profiles


def chemistry(
    players: list[PlayerProfile], manager_tenure_years: float
) -> dict[tuple[str, str], float]:
    """Pairwise on-pitch familiarity in [0, 1] (deterministic).

    Rises with years playing together at the club, a shared academy, a shared language,
    and the manager's tenure (a settled system).
    """
    out: dict[tuple[str, str], float] = {}
    for i, a in enumerate(players):
        for b in players[i + 1 :]:
            together = 0
            both_academy = False
            if a.origin is not None and b.origin is not None:
                together = max(0, SEASON_YEAR - max(a.origin.joined_year, b.origin.joined_year))
                both_academy = a.origin.kind == "academy" and b.origin.kind == "academy"
            same_language = language_of(a.career.nationality) == language_of(b.career.nationality)
            z = (
                -1.2
                + 0.35 * min(together, 6)
                + (0.6 if both_academy else 0.0)
                + (0.4 if same_language else 0.0)
                + 0.08 * min(manager_tenure_years, 6.0)
            )
            key = (
                (a.player_id, b.player_id)
                if a.player_id < b.player_id
                else (b.player_id, a.player_id)
            )
            out[key] = rating(z)
    return out
