from functools import cache

import numpy as np

from matchmind.league.league import build_league
from matchmind.league.profiles import build_club_profiles, build_player_profiles, chemistry
from matchmind.schemas_profile import Origin, PlayerProfile


@cache
def _clubs(seed: int = 2026):
    league = build_league(seed)
    return league, build_club_profiles(league, seed)


def test_club_profiles_deterministic():
    assert _clubs(3)[1] == build_club_profiles(build_league(3), 3)


def test_promoted_clubs_and_last_finish():
    _, clubs = _clubs()
    promoted = [c for c in clubs.values() if c.status == "promoted"]
    assert len(promoted) == 3 and all(c.last_finish is None for c in promoted)
    finishes = sorted(c.last_finish for c in clubs.values() if c.last_finish is not None)
    assert finishes == list(range(1, 18))


def test_status_mix():
    _, clubs = _clubs()
    statuses = [c.status for c in clubs.values()]
    assert statuses.count("title_contender") == 4
    assert 3 <= statuses.count("relegation_fight") <= 6


def test_budgets_right_skewed_and_follow_strength():
    league, clubs = _clubs()
    budgets = np.array([c.transfer_budget_m for c in clubs.values()])
    assert budgets.mean() > np.median(budgets)
    assert budgets.max() / budgets.min() > 4
    assert 2.0 <= float(np.median(budgets)) <= 8.0  # Colombian-league scale, USD millions
    wages = np.array([c.wage_bill_m for c in clubs.values()])
    assert 5.0 <= float(np.median(wages)) <= 20.0
    old_money = [c for c in clubs.values() if c.ownership != "new_owner"]
    strength = [league.strength[c.club_id] for c in old_money]
    assert np.corrcoef(strength, [np.log(c.transfer_budget_m) for c in old_money])[0, 1] > 0.5


def test_ownership_and_culture_consistent():
    _, clubs = _clubs()
    new_owners = [c for c in clubs.values() if c.ownership == "new_owner"]
    assert len(new_owners) == 3 and all(c.owner_since >= 2025 for c in new_owners)
    for c in clubs.values():
        assert (c.ownership == "fan_owned") == (c.culture == "fan_owned")


def test_tactical_identity_follows_manager_style():
    by_style: dict[str, list] = {}
    for seed in range(1, 13):
        for c in _clubs(seed)[1].values():
            by_style.setdefault(c.management.manager_style, []).append(c.tactical_identity)

    def mean(style, field):
        return float(np.mean([getattr(t, field) for t in by_style[style]]))

    assert mean("pressing", "press_intensity") > mean("counter", "press_intensity") + 0.2
    assert mean("pressing", "line_height") > mean("counter", "line_height") + 0.2
    assert mean("counter", "directness") > mean("possession", "directness") + 0.2
    builds = {t.build_up for t in by_style["possession"]}
    assert "short" in builds


def test_tactical_ratings_bounded_and_varied():
    _, clubs = _clubs()
    press = [c.tactical_identity.press_intensity for c in clubs.values()]
    assert min(press) >= 0.0 and max(press) <= 1.0 and np.std(press) > 0.08


def _with_origin(profile, joined: int, kind: str = "signed"):
    origin = Origin(
        kind=kind, joined_year=joined, signed_from=None, fee_m=0.0, club_apps=0, club_goals=0
    )
    return profile.model_copy(update={"origin": origin})


def test_chemistry_rises_with_shared_history():
    league = build_league()
    profiles = build_player_profiles(league, seed=2026)
    squad = [profiles[p.player_id] for p in league.squads["laureles"]]
    a, b, c = squad[2], squad[3], squad[4]
    base = {"career": a.career.model_copy(update={"nationality": "COL"})}
    a = _with_origin(a.model_copy(update=base), 2020)
    b = _with_origin(
        b.model_copy(update={"career": b.career.model_copy(update={"nationality": "COL"})}), 2020
    )
    c = _with_origin(
        c.model_copy(update={"career": c.career.model_copy(update={"nationality": "BRA"})}), 2026
    )
    chem = chemistry([a, b, c], manager_tenure_years=2.0)
    key = lambda x, y: tuple(sorted((x.player_id, y.player_id)))  # noqa: E731
    assert len(chem) == 3 and all(0.0 <= v <= 1.0 for v in chem.values())
    assert chem[key(a, b)] > chem[key(a, c)]  # years together + shared language

    academy_a = _with_origin(a, 2020, "academy")
    academy_b = _with_origin(b, 2020, "academy")
    chem2 = chemistry([academy_a, academy_b], manager_tenure_years=2.0)
    assert chem2[key(a, b)] > chem[key(a, b)]

    longer_manager = chemistry([a, b], manager_tenure_years=6.0)
    assert longer_manager[key(a, b)] > chem[key(a, b)]


def test_chemistry_compatriots_above_shared_language():
    league = build_league()
    profiles = build_player_profiles(league, seed=2026)
    a, b, c = (profiles[p.player_id] for p in league.squads["laureles"][2:5])

    def nat(p: PlayerProfile, code: str) -> PlayerProfile:
        return _with_origin(
            p.model_copy(update={"career": p.career.model_copy(update={"nationality": code})}),
            2022,
        )

    a, b, c = nat(a, "COL"), nat(b, "COL"), nat(c, "PER")  # all Spanish speakers
    chem = chemistry([a, b, c], manager_tenure_years=2.0)
    key = lambda x, y: tuple(sorted((x.player_id, y.player_id)))  # noqa: E731
    assert chem[key(a, b)] > chem[key(a, c)]
