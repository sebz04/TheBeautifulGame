from functools import cache

import numpy as np
import pytest

from matchmind.engine.modifiers import (
    STORYLINE_CAP,
    SUBTLE_CAP,
    MatchContext,
    Modifiers,
    match_form,
    pair_mods,
)
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles
from matchmind.schemas_profile import ClubProfile, PlayerProfile, Profiles


@cache
def _profiles() -> Profiles:
    return build_profiles(build_league(), seed=2026)


def _player(**changes: dict[str, object]) -> tuple[PlayerProfile, ClubProfile]:
    """A real profile with selected sub-models overridden, e.g. personality={...}."""
    profs = _profiles()
    p = profs.players["ala-10"]
    update = {k: getattr(p, k).model_copy(update=v) for k, v in changes.items()}
    p = p.model_copy(update=update)
    return p, profs.clubs[p.club_id]


def _mult(name: str, ctx: MatchContext | None = None, **changes: dict[str, object]) -> float:
    p, club = _player(**changes)
    return getattr(Modifiers.for_player(p, club, ctx or MatchContext()), name)


def test_caps_hold_for_every_player_and_context() -> None:
    profs = _profiles()
    contexts = [
        MatchContext(),
        MatchContext(
            minute=88,
            score_diff=0,
            is_home=False,
            energy=0.1,
            confidence=0.0,
            congestion_days=3,
            form=-3.0,
        ),  # fmt: skip
        MatchContext(minute=10, score_diff=3, energy=1.0, confidence=1.0, form=3.0),
    ]
    for p in profs.players.values():
        club = profs.clubs[p.club_id]
        for ctx in contexts:
            for storyline, cap in ((False, SUBTLE_CAP), (True, STORYLINE_CAP)):
                mods = Modifiers.for_player(
                    p, club, ctx.model_copy(update={"storyline": storyline})
                )
                assert all(abs(e) <= cap + 1e-12 for e in mods.effects.values()), p.player_id


@pytest.mark.parametrize(
    ("name", "sub", "field", "higher_means"),
    [
        ("decision_temperature", "personality", "composure", "lower"),
        ("tackle_rate", "personality", "aggression", "higher"),
        ("foul_rate", "personality", "aggression", "higher"),
        ("press_urgency", "personality", "aggression", "higher"),
        ("shot_rate", "personality", "confidence", "higher"),
        ("teammate_composure", "personality", "leadership", "higher"),
        ("offball_distance", "style", "work_rate", "higher"),
        ("energy_drain", "style", "work_rate", "higher"),
        ("anchor_tightness", "style", "tactical_discipline", "higher"),
        ("run_timing_sd", "style", "tactical_discipline", "lower"),
        ("run_timing_sd", "personality", "composure", "lower"),
        ("risk_weight", "style", "risk_tolerance", "higher"),
        ("pass_error", "technical", "passing", "lower"),
        ("touch_error", "technical", "first_touch", "lower"),
        ("dribble_error", "technical", "dribbling", "lower"),
        ("shot_error", "technical", "finishing", "lower"),
        ("cross_error", "technical", "crossing", "lower"),
        ("tackle_error", "technical", "tackling", "lower"),
        ("aerial_error", "technical", "aerial", "lower"),
        ("gk_error", "technical", "shot_stopping", "lower"),
        ("distribution_error", "technical", "distribution", "lower"),
    ],
)
def test_directions(name: str, sub: str, field: str, higher_means: str) -> None:
    low = _mult(name, **{sub: {field: 0.2}})
    high = _mult(name, **{sub: {field: 0.8}})
    assert (high > low) if higher_means == "higher" else (high < low), (name, field)


def test_pressure_amplifies_composure() -> None:
    calm, nervy = {"composure": 0.9}, {"composure": 0.1}
    early = MatchContext(minute=20, score_diff=2)
    late_close = MatchContext(minute=85, score_diff=0)
    gap_early = _mult("decision_temperature", early, personality=nervy) - _mult(
        "decision_temperature", early, personality=calm)  # fmt: skip
    gap_late = _mult("decision_temperature", late_close, personality=nervy) - _mult(
        "decision_temperature", late_close, personality=calm)  # fmt: skip
    assert gap_late > gap_early > 0


def test_confidence_state_and_home_advantage() -> None:
    assert _mult("shot_rate", MatchContext(confidence=0.9)) > _mult(
        "shot_rate", MatchContext(confidence=0.1)
    )
    home = _mult("decision_temperature", MatchContext(is_home=True))
    away = _mult("decision_temperature", MatchContext(is_home=False))
    assert home <= away  # home crowd steadies decisions (club home_advantage >= 0.5 adds)


def test_fatigue_loosens_run_timing_and_injury_lowers_start_energy() -> None:
    assert _mult("run_timing_sd", MatchContext(energy=0.2)) > _mult(
        "run_timing_sd", MatchContext(energy=1.0)
    )
    fit = _mult("start_energy", status={"injury": "fit"})
    back = _mult("start_energy", status={"injury": "returning"})
    assert back < fit == 1.0
    assert _mult("start_energy", MatchContext(congestion_days=3)) < fit


def test_veterans_time_runs_better() -> None:
    rookie = _mult("run_timing_sd", career={"years_pro": 1})
    veteran = _mult("run_timing_sd", career={"years_pro": 13})
    assert veteran < rookie


def test_storyline_is_at_least_three_times_subtle() -> None:
    subtle = _mult("foul_rate", personality={"aggression": 0.95}) - 1
    story = _mult("foul_rate", MatchContext(storyline=True), personality={"aggression": 0.95}) - 1
    assert subtle > 0 and story >= 3 * subtle


def test_match_form_variance_follows_consistency() -> None:
    steady, _ = _player(personality={"consistency": 0.9})
    erratic, _ = _player(personality={"consistency": 0.1})
    rng = np.random.default_rng(1)
    steady_forms = [match_form(steady, rng) for _ in range(3000)]
    erratic_forms = [match_form(erratic, rng) for _ in range(3000)]
    assert np.std(erratic_forms) > 1.5 * np.std(steady_forms)
    assert _mult("form", MatchContext(form=1.0)) > 1.0 > _mult("form", MatchContext(form=-1.0))


def test_pair_chemistry() -> None:
    good, bad = pair_mods(0.9), pair_mods(0.1)
    assert good.completion > 1.0 > bad.completion
    assert good.run_early > bad.run_early
    assert abs(pair_mods(1.0, storyline=False).completion - 1) <= SUBTLE_CAP + 1e-12


def test_mods_recorded_in_extras() -> None:
    p, club = _player(personality={"aggression": 0.95, "composure": 0.5})
    extras = Modifiers.for_player(p, club, MatchContext()).to_extras()
    assert extras["foul_rate"] > 0.01
    assert all(abs(v) > 0.01 for v in extras.values())
    assert all(round(v, 3) == v for v in extras.values())


def test_team_mods_tactics_uncapped_and_chasing() -> None:
    profs = _profiles()
    club = profs.clubs["laureles"]
    team = Modifiers.for_team(club, MatchContext())
    tactic = club.tactical_identity
    assert (team.press_intensity, team.line_height, team.directness) == (
        tactic.press_intensity, tactic.line_height, tactic.directness)  # fmt: skip
    losing_late = Modifiers.for_team(club, MatchContext(minute=75, score_diff=-1))
    assert losing_late.chase_urgency > team.chase_urgency == 1.0
    insecure = club.model_copy(update={"management": club.management.model_copy(
        update={"job_security": 0.1})})  # fmt: skip
    secure = club.model_copy(update={"management": club.management.model_copy(
        update={"job_security": 0.9})})  # fmt: skip
    ctx = MatchContext(minute=75, score_diff=-1)
    assert (
        Modifiers.for_team(insecure, ctx).chase_urgency
        > Modifiers.for_team(secure, ctx).chase_urgency
    )
    assert abs(losing_late.chase_urgency - 1) <= SUBTLE_CAP + 1e-12


def test_extras_can_be_limited_to_the_action() -> None:
    p, club = _player(personality={"aggression": 0.95}, technical={"tackling": 0.9})
    mods = Modifiers.for_player(p, club, MatchContext())
    tackle = mods.to_extras(only=("tackle_rate", "foul_rate", "tackle_error"))
    assert set(tackle) == {"tackle_rate", "foul_rate", "tackle_error"}
