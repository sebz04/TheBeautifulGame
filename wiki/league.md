# League, Profiles and Fixtures

**Status:** TASK-3.1 (clubs, squads, fixtures) and TASK-3.2 (player profiles) and TASK-3.3 (club profiles, chemistry) done. Origins, transfers and legends: TASK-3.4.

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

## Player profiles (`schemas_profile.py`, `league/profiles.py`)
`build_player_profiles(league, seed) -> dict[player_id, PlayerProfile]`. `PlayerProfile` = `personality` (composure, aggression, confidence, leadership, consistency), `style` (position, secondary_position, role from 19 options, work_rate, tactical_discipline, risk_tolerance), `technical` (passing, first_touch, dribbling, finishing, crossing, tackling, aerial, shot_stopping, distribution), `career` (nationality, birth_year, years_pro, stage, caps, contract_until 2027–2031, market_value_m, contract_negotiations, transfer_interest, retirement_risk, previous_league_clubs), `discipline`, `status` (injury, games_missed, captain, foot, height), `origin` (added in TASK-3.4). Flags (`is_academy`, `is_new_signing`, `is_former_rival`, `is_returning_from_injury`) are computed fields, so they can't disagree with the data.

How attributes come from the latents (weights in `profiles.py`):
- composure ← mentality, quality, −temperament, experience · aggression ← temperament (+DF, −GK) · leadership ← mentality, experience · consistency ← mentality, experience
- technical ← quality + position priors (`_TECH_TABLE`); aerial uses height; outfield shot_stopping ≈ 0
- market value: log-normal, `ln(4) + 1.1·quality + age term + noise` (young players get a potential premium; over 30, value declines)
- discipline: Poisson cards from career apps × (position base + aggression)
- captain: highest leadership in the squad among players aged 24+

Seed-2026 check: traits mean ≈ 0.50, SD ≈ 0.16, under 2% beyond 0.15/0.85; aggression > 0.8 = 1.75%; market value median $3.9m, mean $8.4m, 1.75% above $50m, max $133m; 9.5% injured or doubtful; 18 roles used.

## Club profiles and chemistry (`league/profiles.py`)
`build_club_profiles(league, seed) -> dict[club_id, ClubProfile]`.
- **Status:** the top 4 by strength are `title_contender`; 3 clubs drawn from the bottom 7 are `promoted` (`last_finish = None`); the rest of the bottom 8 are `relegation_fight`; everyone else is `mid_table`. `last_finish` (1–17) = strength rank plus noise.
- **Manager style** is drawn with weights by status, and **tactical identity** comes from style priors (`_STYLE_PRIORS`: pressing → high press and line; counter → low line, direct; possession → short build-up) plus noise. `build_up` comes from directness.
- **Management:** tenure is exponential (mean 2.2 years, 0.2–12); job security comes from tenure plus over- or under-performance against expected rank.
- **Ownership:** 3 `new_owner` (owner since 2025–26, budget × 2.5, usually `win_now`), 2 `fan_owned` (culture `fan_owned`), the rest `long_standing`.
- **Money:** budget is log-normal (median $35m × e^(0.6·strength)), promoted clubs get × 0.6; wage bill is log-normal (median $70m).
- **Home advantage:** from stadium capacity (+ fan ownership).

`chemistry(players, manager_tenure_years) -> {(a, b): rating}` is deterministic and pairwise (sorted ids). It rises with years together (from `origin.joined_year`, capped at 6), both being academy players, a shared language (`names.language_of`), and manager tenure.
