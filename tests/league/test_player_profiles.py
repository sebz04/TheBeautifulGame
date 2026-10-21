"""Player profiles must look like a real league: bell-shaped traits, right-skewed money."""

from collections import Counter
from functools import cache

import numpy as np
import pytest

from matchmind.league.league import build_league
from matchmind.league.profiles import build_player_profiles
from matchmind.schemas_profile import SEASON_YEAR

BELL_FIELDS = {
    "personality": ["composure", "aggression", "confidence", "leadership", "consistency"],
    "style": ["work_rate", "tactical_discipline", "risk_tolerance"],
}


@cache
def _data():
    league = build_league()
    return league, build_player_profiles(league, seed=2026)


def _values(group: str, field: str) -> np.ndarray:
    _, profiles = _data()
    return np.array([getattr(getattr(p, group), field) for p in profiles.values()])


def test_profiles_deterministic():
    league = build_league()
    assert build_player_profiles(league, seed=1) == build_player_profiles(league, seed=1)
    assert build_player_profiles(league, seed=1) != build_player_profiles(league, seed=2)


def test_one_profile_per_player():
    league, profiles = _data()
    ids = {p.player_id for squad in league.squads.values() for p in squad}
    assert set(profiles) == ids
    club_of = {p.player_id: p.club_id for squad in league.squads.values() for p in squad}
    assert all(prof.club_id == club_of[pid] for pid, prof in profiles.items())


@pytest.mark.parametrize(("group", "field"), [(g, f) for g, fs in BELL_FIELDS.items() for f in fs])
def test_rating_distributions_are_bell_shaped(group, field):
    v = _values(group, field)
    assert 0.40 <= v.mean() <= 0.60, v.mean()
    assert 0.10 <= v.std() <= 0.22, v.std()
    assert (v > 0.85).mean() < 0.05 and (v < 0.15).mean() < 0.05
    skew = float(((v - v.mean()) ** 3).mean() / v.std() ** 3)
    assert abs(skew) < 0.6, skew


def test_short_tempered_players_are_rare():
    aggression = _values("personality", "aggression")
    assert 0.005 <= (aggression > 0.8).mean() <= 0.06


def test_technical_ratings_follow_position():
    league, profiles = _data()
    by_pos: dict[str, list] = {}
    for squad in league.squads.values():
        for p in squad:
            by_pos.setdefault(p.position, []).append(profiles[p.player_id].technical)

    def mean(pos, field):
        return float(np.mean([getattr(t, field) for t in by_pos[pos]]))

    assert mean("FW", "finishing") > mean("MF", "finishing") > mean("DF", "finishing")
    assert mean("DF", "tackling") > mean("FW", "tackling")
    assert mean("MF", "passing") > mean("DF", "passing")
    assert mean("GK", "shot_stopping") > 0.5 > 0.1 > mean("DF", "shot_stopping")
    outfield_passing = [t.passing for pos in ("DF", "MF", "FW") for t in by_pos[pos]]
    assert 0.40 <= float(np.mean(outfield_passing)) <= 0.62


def test_money_is_right_skewed():
    value = np.array([p.career.market_value_m for p in _data()[1].values()])
    assert 2.0 <= float(np.median(value)) <= 8.0
    assert (value > 50).mean() < 0.03
    assert value.mean() > np.median(value) * 1.2
    assert value.min() >= 0.1 and value.max() < 200


def test_demographics():
    league, profiles = _data()
    ages = np.array([SEASON_YEAR - p.career.birth_year for p in profiles.values()])
    assert 25.5 <= ages.mean() <= 27.8 and 3.5 <= ages.std() <= 5.0
    assert ages.min() >= 16 and ages.max() <= 38
    heights: dict[str, list[int]] = {}
    for squad in league.squads.values():
        for p in squad:
            heights.setdefault(p.position, []).append(profiles[p.player_id].status.height_cm)
    mean_h = {k: np.mean(v) for k, v in heights.items()}
    assert mean_h["GK"] > mean_h["DF"] > mean_h["MF"]
    assert 186 <= mean_h["GK"] <= 194 and 175 <= mean_h["MF"] <= 182
    feet = Counter(p.status.preferred_foot for p in profiles.values())
    assert 0.15 <= feet["left"] / 400 <= 0.30 and feet["both"] / 400 <= 0.06
    not_fit = sum(p.status.injury != "fit" for p in profiles.values()) / 400
    assert 0.05 <= not_fit <= 0.18
    usa = sum(p.career.nationality == "USA" for p in profiles.values()) / 400
    assert 0.30 <= usa <= 0.50
    assert {p.career.contract_until for p in profiles.values()} <= set(range(2027, 2032))


def test_career_stage_rule():
    for p in _data()[1].values():
        if p.career.years_pro <= 2:
            assert p.career.stage == "rookie"
        elif p.career.years_pro >= 10:
            assert p.career.stage == "veteran"
        else:
            assert p.career.stage == "prime"


def _corr(a, b) -> float:
    return float(np.corrcoef(np.asarray(a, float), np.asarray(b, float))[0, 1])


def test_correlations_match_real_life():
    league, profiles = _data()
    profs = list(profiles.values())
    per_year = [p.discipline.career_yellows / max(p.career.years_pro, 1) for p in profs]
    assert _corr([p.personality.aggression for p in profs], per_year) > 0.3
    players = {p.player_id: p for squad in league.squads.values() for p in squad}
    assert (
        _corr(
            [players[p.player_id].skill for p in profs],
            [np.log(p.career.market_value_m) for p in profs],
        )
        > 0.4
    )
    vets = [p.personality.leadership for p in profs if p.career.stage == "veteran"]
    rookies = [p.personality.leadership for p in profs if p.career.stage == "rookie"]
    assert np.mean(vets) > np.mean(rookies) + 0.08
    outfield = [p for p in profs if p.style.position != "GK"]
    assert (
        _corr(
            [players[p.player_id].skill for p in outfield], [p.technical.passing for p in outfield]
        )
        > 0.4
    )
    old = [p.career.retirement_risk for p in profs if SEASON_YEAR - p.career.birth_year >= 33]
    young = [p.career.retirement_risk for p in profs if SEASON_YEAR - p.career.birth_year <= 28]
    assert np.mean(old) > 0.4 > 0.1 > np.mean(young)


def test_one_captain_per_club_with_high_leadership():
    league, profiles = _data()
    for squad in league.squads.values():
        captains = [p for p in squad if profiles[p.player_id].status.captain]
        assert len(captains) == 1
        lead = [profiles[p.player_id].personality.leadership for p in squad]
        assert profiles[captains[0].player_id].personality.leadership >= np.percentile(lead, 75)


def test_roles_fit_slots():
    league, profiles = _data()
    allowed = {
        "GK": {"sweeper_keeper", "shot_stopper"},
        "DF": {"ball_playing_cb", "stopper", "fullback", "wingback", "inverted_fullback"},
        "MF": {
            "anchor",
            "deep_playmaker",
            "box_to_box",
            "playmaker",
            "advanced_playmaker",
            "shadow_striker",
        },
        "FW": {
            "winger",
            "inside_forward",
            "target_man",
            "poacher",
            "false_nine",
            "pressing_forward",
        },
    }
    for squad in league.squads.values():
        for p in squad:
            assert profiles[p.player_id].style.role in allowed[p.position]
    roles = Counter(prof.style.role for prof in profiles.values())
    assert len(roles) >= 15  # variety across the league


def test_some_players_have_caps_and_transfer_interest():
    profs = list(_data()[1].values())
    capped = sum(p.career.caps > 0 for p in profs) / len(profs)
    assert 0.15 <= capped <= 0.6
    wanted = [p for p in profs if p.career.transfer_interest]
    assert 0.03 <= len(wanted) / len(profs) <= 0.25
    assert all(p.club_id not in p.career.transfer_interest for p in wanted)
