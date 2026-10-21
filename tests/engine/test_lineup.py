from collections import Counter

from matchmind.engine.lineup import FORMATION_LINES, match_meta, starting_xi
from matchmind.league.clubs import CLUBS
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league


def test_starting_xi_follows_formation() -> None:
    league = build_league()
    squad = league.squads["chapinero"]
    for formation, (df, mf, fw) in FORMATION_LINES.items():
        xi = starting_xi(squad, formation)
        assert len(xi) == 11 == len({p.player_id for p in xi})
        assert Counter(p.position for p in xi) == {"GK": 1, "DF": df, "MF": mf, "FW": fw}
        assert xi[0].position == "GK"


def test_match_meta_deterministic_and_complete() -> None:
    league = build_league()
    fixture = build_fixtures(league, seed=2026)[0]
    meta = match_meta(league, fixture, seed=7)
    assert meta == match_meta(league, fixture, seed=7)
    assert meta.match_id == fixture.match_id and meta.seed == 7
    assert meta.home.club_id == fixture.home_id and meta.away.club_id == fixture.away_id
    assert meta.kickoff_iso.startswith(fixture.date)
    stadium = {c.club_id: c.stadium for c in CLUBS}[fixture.home_id]
    assert meta.stadium == stadium
    assert 60 <= meta.added_time_s[0] <= 300 and 120 <= meta.added_time_s[1] <= 480
    for club, squad in ((meta.home, meta.home_squad), (meta.away, meta.away_squad)):
        assert len(squad) == 20  # starting XI first, then the bench
        assert squad[:11] == starting_xi(league.squads[club.club_id], club.formation)
