from collections import Counter, defaultdict
from functools import cache

import numpy as np

from matchmind.league.clubs import derby_rival
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles
from matchmind.schemas_profile import SEASON_YEAR


@cache
def _data():
    league = build_league()
    return league, build_profiles(league, seed=2026)


def test_build_profiles_deterministic():
    league = build_league()
    assert build_profiles(league, seed=5) == build_profiles(league, seed=5)


def test_every_player_has_an_origin():
    _, prof = _data()
    assert all(p.origin is not None for p in prof.players.values())
    assert set(prof.clubs) == {c.club_id for c in _data()[0].clubs}


def test_origin_mix_is_realistic():
    _, prof = _data()
    kinds = Counter(p.origin.kind for p in prof.players.values())
    n = len(prof.players)
    assert 0.15 <= kinds["academy"] / n <= 0.35
    assert 0.03 <= kinds["loan"] / n <= 0.12
    signings = kinds["signed"] + kinds["free"]
    assert 0.10 <= kinds["free"] / signings <= 0.25
    new = sum(p.is_new_signing for p in prof.players.values()) / n
    assert 0.15 <= new <= 0.40


def test_transfer_chain_ends_at_current_club():
    _, prof = _data()
    by_player = defaultdict(list)
    for t in prof.transfers:
        by_player[t.player_id].append(t)
    for pid, p in prof.players.items():
        chain = sorted(by_player[pid], key=lambda t: t.year)
        if p.origin.kind == "academy":
            assert chain == []
            continue
        last = chain[-1]
        assert last.to_club == p.club_id and last.year == p.origin.joined_year
        assert last.from_club == p.origin.signed_from
        expected_kind = {"signed": "permanent", "free": "free", "loan": "loan"}[p.origin.kind]
        assert last.kind == expected_kind
        years = [t.year for t in chain]
        assert years == sorted(set(years))
        for prev, nxt in zip(chain, chain[1:], strict=False):
            assert prev.to_club == nxt.from_club
        in_league = [t.from_club for t in chain if not t.from_club.startswith("ext:")]
        assert in_league == p.career.previous_league_clubs


def test_former_rival_flag_matches_history():
    _, prof = _data()
    flagged = 0
    for p in prof.players.values():
        rival = derby_rival(p.club_id)
        assert p.is_former_rival == (rival is not None and rival in p.career.previous_league_clubs)
        flagged += p.is_former_rival
    assert flagged >= 1  # at least one derby storyline exists


def test_fees_are_right_skewed_and_track_value():
    _, prof = _data()
    permanent = [p for p in prof.players.values() if p.origin.kind == "signed"]
    fees = np.array([p.origin.fee_m for p in permanent])
    assert 0.2 <= float(np.median(fees)) <= 1.2
    assert fees.mean() > np.median(fees) and 3 < fees.max() < 25
    values = np.log([p.career.market_value_m for p in permanent])
    assert np.corrcoef(np.log(fees + 0.1), values)[0, 1] > 0.4
    for p in prof.players.values():
        if p.origin.kind in ("academy", "free"):
            assert p.origin.fee_m == 0.0


def test_loans_are_short_and_never_captain():
    _, prof = _data()
    for p in prof.players.values():
        if p.origin.kind == "loan":
            assert not p.status.captain
            assert p.career.contract_until == SEASON_YEAR + 1
            assert p.origin.joined_year == SEASON_YEAR


def test_club_records_and_legends():
    _, prof = _data()
    legends = defaultdict(list)
    for leg in prof.legends:
        legends[leg.club_id].append(leg)
    assert set(legends) == set(prof.clubs)
    for club_id, pair in legends.items():
        assert sorted(leg.record for leg in pair) == ["appearances", "goals"]
        scorer = next(leg for leg in pair if leg.record == "goals")
        apps = next(leg for leg in pair if leg.record == "appearances")
        current = [p.origin.club_goals for p in prof.players.values() if p.club_id == club_id]
        assert scorer.goals > max(current)
        assert 100 <= scorer.goals <= 260 and 400 <= apps.apps <= 700
        assert scorer.era.endswith("s") and scorer.era[:4].isdigit()


def test_new_signings_have_no_prior_club_apps():
    _, prof = _data()
    for p in prof.players.values():
        if p.origin.joined_year == SEASON_YEAR:
            assert p.origin.club_apps == 0
    academy_vets = [
        p.origin.club_apps
        for p in prof.players.values()
        if p.origin.kind == "academy" and p.career.years_pro >= 8
    ]
    assert np.mean(academy_vets) > 150
