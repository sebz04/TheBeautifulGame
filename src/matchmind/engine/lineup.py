"""Starting line-ups and match setup: league + fixture + seed -> `MatchMeta`."""

from matchmind.league.clubs import CLUBS
from matchmind.league.dist import stream
from matchmind.league.fixtures import Fixture
from matchmind.league.league import League
from matchmind.schemas import MatchMeta, Player

ENGINE_VERSION = "l1-0.1"
KICKOFF_LOCAL = "T19:30:00-05:00"  # Colombia time (UTC-5, no daylight saving)

# Outfield players per line: (DF, MF, FW).
FORMATION_LINES: dict[str, tuple[int, int, int]] = {
    "4-3-3": (4, 3, 3),
    "4-2-3-1": (4, 5, 1),
    "4-4-2": (4, 4, 2),
    "3-5-2": (3, 5, 2),
}


def _by_skill(players: list[Player]) -> list[Player]:
    return sorted(players, key=lambda p: (-p.skill, p.player_id))


def starting_xi(squad: list[Player], formation: str) -> list[Player]:
    """The best keeper, then the best players per line, ordered GK, DF, MF, FW.

    Within a line players are ordered by squad id, which maps them onto formation slots.
    """
    df, mf, fw = FORMATION_LINES[formation]
    xi = _by_skill([p for p in squad if p.position == "GK"])[:1]
    for position, n in (("DF", df), ("MF", mf), ("FW", fw)):
        picked = _by_skill([p for p in squad if p.position == position])[:n]
        xi += sorted(picked, key=lambda p: p.player_id)
    return xi


def _ordered_squad(squad: list[Player], formation: str) -> list[Player]:
    xi = starting_xi(squad, formation)
    chosen = {p.player_id for p in xi}
    return xi + [p for p in squad if p.player_id not in chosen]


def _available(league: League, club_id: str, unavailable: frozenset[str]) -> list[Player]:
    return [p for p in league.squads[club_id] if p.player_id not in unavailable]


def match_meta(
    league: League,
    fixture: Fixture,
    seed: int,
    scenario_id: str = "none",
    unavailable: frozenset[str] = frozenset(),
) -> MatchMeta:
    """Squads are ordered starting XI first (GK, DF, MF, FW), then the bench.

    `unavailable` players (suspended) are left out of both.
    """
    rng = stream(seed, f"meta:{fixture.match_id}")
    clubs = {c.club_id: c for c in league.clubs}
    home, away = clubs[fixture.home_id], clubs[fixture.away_id]
    stadium = {c.club_id: c.stadium for c in CLUBS}[home.club_id]
    added = (float(rng.integers(1, 5)) * 60.0, float(rng.integers(3, 8)) * 60.0)
    added = (added[0] + float(rng.integers(0, 60)), added[1] + float(rng.integers(0, 60)))
    return MatchMeta(
        match_id=fixture.match_id,
        seed=seed,
        home=home,
        away=away,
        home_squad=_ordered_squad(_available(league, home.club_id, unavailable), home.formation),
        away_squad=_ordered_squad(_available(league, away.club_id, unavailable), away.formation),
        scenario_id=scenario_id,
        engine_version=ENGINE_VERSION,
        stadium=stadium,
        kickoff_iso=fixture.date + KICKOFF_LOCAL,
        added_time_s=added,
    )
