from collections import Counter
from pathlib import Path

from matchmind.league.clubs import CLUBS, derbies
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _blocklist(name: str) -> list[str]:
    lines = (FIXTURES / name).read_text().splitlines()
    return [ln.strip().lower() for ln in lines if ln.strip() and not ln.startswith("#")]


def test_twenty_approved_clubs():
    names = [c.name for c in CLUBS]
    assert len(names) == 20 == len(set(names))
    assert "Boyle Heights Athletic" in names and "Watts Union" in names
    assert len({c.short for c in CLUBS}) == 20
    assert all(len(c.short) == 3 and c.short.isupper() for c in CLUBS)


def test_derbies_are_neighbors():
    ids = {c.club_id for c in CLUBS}
    pairs = derbies()
    assert ("echo-park", "silver-lake") in pairs
    assert len(pairs) == 4
    assert all(a in ids and b in ids for a, b in pairs)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _dist(a: str, b: str) -> float:
    return sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b), strict=True)) ** 0.5


def test_kits_are_distinguishable():
    by_id = {c.club_id: c for c in CLUBS}
    for a, b in derbies():
        assert _dist(by_id[a].primary_color, by_id[b].primary_color) > 100
    for i, a in enumerate(CLUBS):
        for b in CLUBS[i + 1 :]:
            combined = (
                _dist(a.primary_color, b.primary_color) ** 2
                + _dist(a.secondary_color, b.secondary_color) ** 2
            ) ** 0.5
            assert combined > 60, (a.name, b.name)


def test_league_deterministic():
    assert build_league(seed=7) == build_league(seed=7)
    assert build_league(seed=7) != build_league(seed=8)


def test_league_shape():
    league = build_league()
    assert len(league.clubs) == 20
    all_ids = []
    for club in league.clubs:
        squad = league.squads[club.club_id]
        assert len(squad) == 20
        assert Counter(p.position for p in squad) == {"GK": 2, "DF": 7, "MF": 7, "FW": 4}
        assert len({p.number for p in squad}) == 20
        assert all(p.club_id == club.club_id for p in squad)
        all_ids += [p.player_id for p in squad]
    assert len(all_ids) == len(set(all_ids)) == 400
    assert set(league.latents) == set(all_ids)


def test_goalkeepers_wear_keeper_numbers():
    league = build_league()
    for squad in league.squads.values():
        gk_numbers = sorted(p.number for p in squad if p.position == "GK")
        assert gk_numbers[0] == 1


def test_no_real_names():
    blocked = _blocklist("real_club_blocklist.txt")
    full = {b for b in blocked if ":" not in b}
    nicknames = {b.split(":", 1)[1] for b in blocked if b.startswith("nickname:")}
    words = {b.split(":", 1)[1] for b in blocked if b.startswith("word:")}
    for club in CLUBS:
        lower = club.name.lower()
        assert lower not in full
        assert not any(lower.endswith(" " + n) for n in nicknames), club.name
        assert not any(w in lower for w in words), club.name
    players = _blocklist("real_player_blocklist.txt")
    full_players = {b for b in players if ":" not in b}
    surnames = {b.split(":", 1)[1] for b in players if b.startswith("surname:")}
    for squad in build_league().squads.values():
        for p in squad:
            assert p.name.lower() not in full_players, p.name
            assert p.name.lower().split()[-1] not in surnames, p.name


def test_fixtures_round_robin():
    league = build_league()
    fixtures = build_fixtures(league, seed=2026)
    assert len(fixtures) == 380
    by_round = Counter(f.round for f in fixtures)
    assert set(by_round) == set(range(1, 39)) and set(by_round.values()) == {10}
    for r in range(1, 39):
        teams = [t for f in fixtures if f.round == r for t in (f.home_id, f.away_id)]
        assert len(teams) == len(set(teams)) == 20
    meetings = Counter((f.home_id, f.away_id) for f in fixtures)
    assert set(meetings.values()) == {1}
    for f in fixtures:
        assert (f.away_id, f.home_id) in meetings
    homes = Counter(f.home_id for f in fixtures)
    assert set(homes.values()) == {19}


def test_fixture_dates_ordered_with_midweek_rounds():
    fixtures = build_fixtures(build_league(), seed=2026)
    dates = {f.round: f.date for f in fixtures}
    assert dates[1] == "2026-08-15"
    ordered = [dates[r] for r in range(1, 39)]
    assert ordered == sorted(ordered) and len(set(ordered)) == 38
    from datetime import date

    gaps = [
        (date.fromisoformat(b) - date.fromisoformat(a)).days
        for a, b in zip(ordered, ordered[1:], strict=False)
    ]
    assert min(gaps) >= 3 and 3 in gaps  # congested midweek rounds exist
