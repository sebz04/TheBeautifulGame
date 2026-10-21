# League, Profiles and Fixtures

**Status:** TASK-3.1 done (clubs, squads, fixtures). Profiles: TASK-3.2–3.4.

## Clubs (`league/clubs.py`)
`CLUBS`: the 20 approved LA neighborhood clubs (`ClubSeed`: id slug, name, 3-letter short, fictional stadium, capacity, founded, curated kit colors, region). `derbies()` lists 4 pairs; `derby_rival(club_id)`. Kits: derby primaries differ by more than 100 RGB units; every kit pair differs (primary + secondary).

## Squads (`league/league.py`)
`build_league(seed=2026) -> League(clubs, squads, latents, strength)`.
- 20 players per club from `SQUAD_SLOTS`: GK×2, CB×4, FB×3, DM×2, CM×3, AM×2, W×2, ST×2 (positions GK/DF/MF/FW = 2/7/7/4).
- Player ids `"{short}-{nn}"` (e.g. `epr-07`); GK #1 plus a backup keeper number from 13/25/31.
- **Latent factors** (`PlayerLatent`, hidden): `quality` (club strength SD 0.45 + individual SD 0.55, standardized), `temperament`, `athleticism`, `mentality` (all ~N(0, 1)), `age` (truncated normal 26.5 ± 4.2, range 17–37; GKs +1.5), `debut_age` (19 ± 1.5), `nationality`, `slot`. `experience` = standardized age; `years_pro` = age − debut age.
- `strength[club_id]`: standardized club strength.
- `Player.pace/skill/stamina` derive from the latents (`skill` = decision quality); age > 29 reduces pace and stamina.

## Distributions (`league/dist.py`)
`rating(z) = sigmoid(0.7·z)`: bell-shaped around 0.5. `combine(rng, mu, terms, noise)` mixes factors and rescales to unit variance. `log_normal_money(...)`: right-skewed USD millions. `stream(seed, name)`: an independent reproducible RNG per generator part.

## Names (`league/names.py`)
Nationality weights fit an LA league (USA 40%, Mexico 13%, ...). First names are common given names; surnames are composed from syllables, so names are fictional. Korean names are family name first. `language_of(nat)` feeds chemistry. Blocklists: `tests/fixtures/real_*_blocklist.txt`.

## Fixtures (`league/fixtures.py`)
`build_fixtures(league, seed, start_date="2026-08-15") -> list[Fixture(match_id, round, date, home_id, away_id)]`: circle-method double round robin, 38 rounds × 10 matches, each club 19 home. Rounds 5, 12, 19, 26, 33 are midweek (3 days after the previous round), which creates schedule congestion. `match_id = "r{round:02d}-{home}-v-{away}"`.
