"""38-round double round robin with dates, including congested midweek rounds."""

from datetime import date, timedelta

from pydantic import BaseModel

from matchmind.league.dist import stream
from matchmind.league.league import League

MIDWEEK_ROUNDS = {5, 12, 19, 26, 33}  # played 3 days after the previous round


class Fixture(BaseModel):
    match_id: str
    round: int
    date: str
    home_id: str
    away_id: str


def _round_dates(start: date) -> dict[int, str]:
    dates: dict[int, str] = {1: start.isoformat()}
    current = start
    for r in range(2, 39):
        if r in MIDWEEK_ROUNDS:
            current += timedelta(days=3)
        elif r - 1 in MIDWEEK_ROUNDS:
            current += timedelta(days=4)
        else:
            current += timedelta(days=7)
        dates[r] = current.isoformat()
    return dates


def build_fixtures(league: League, seed: int, start_date: str = "2026-08-15") -> list[Fixture]:
    """Circle method: first half (rounds 1-19), then the mirror with venues swapped."""
    teams = [c.club_id for c in league.clubs]
    order = list(stream(seed, "fixtures").permutation(len(teams)))
    teams = [teams[i] for i in order]
    n = len(teams)
    dates = _round_dates(date.fromisoformat(start_date))
    first_half: list[list[tuple[str, str]]] = []
    rotation = teams[:]
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = rotation[i], rotation[n - 1 - i]
            home_first = (r % 2 == 0) if i == 0 else (i % 2 == r % 2)
            pairs.append((a, b) if home_first else (b, a))
        first_half.append(pairs)
        rotation = [rotation[0], rotation[-1], *rotation[1:-1]]

    fixtures: list[Fixture] = []
    for r, pairs in enumerate(first_half, start=1):
        for home, away in pairs:
            fixtures.append(_fixture(r, dates[r], home, away))
        mirror = r + n - 1
        for home, away in pairs:
            fixtures.append(_fixture(mirror, dates[mirror], away, home))
    return sorted(fixtures, key=lambda f: (f.round, f.match_id))


def _fixture(rnd: int, day: str, home: str, away: str) -> Fixture:
    return Fixture(
        match_id=f"r{rnd:02d}-{home}-v-{away}", round=rnd, date=day, home_id=home, away_id=away
    )
