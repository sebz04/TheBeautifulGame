"""`matchmind` command line.

uv run matchmind build --scenario scenarios/comeback_red_card.toml
uv run matchmind build --all            # the 8 storylines
uv run matchmind build --all --season   # also simulate the season history first (once)
"""

import argparse
import sys
from pathlib import Path

from matchmind.config import get_settings
from matchmind.engine.scenario import SCENARIO_DIR
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles
from matchmind.league.season import simulate_history
from matchmind.pipeline.build_match import LEAGUE_SEED, build_scenario
from matchmind.store.blob import tracking_store
from matchmind.store.db import Repo


def _build(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.db:
        settings = settings.model_copy(update={"db_url": args.db})
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    repo, store = Repo(settings.db_url), tracking_store(settings)
    league = build_league(LEAGUE_SEED)
    profiles = build_profiles(league, seed=LEAGUE_SEED)
    if args.season and repo.load_season() is None:
        print("simulating season history (rounds 1-9)...", file=sys.stderr)
        repo.save_season(simulate_history(league, profiles, build_fixtures(league, LEAGUE_SEED)))
    paths = sorted(SCENARIO_DIR.glob("*.toml")) if args.all else [Path(args.scenario)]
    for path in paths:
        r = build_scenario(path, repo, store, league, profiles)
        print(f"{r.scenario_id}: {r.match_id} | {r.events} events, {r.moments} moments "
              f"({r.deviations} deviations), {r.cues} cues, {r.metric_rows} metric rows "
              f"| {r.seconds}s")  # fmt: skip
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="matchmind")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="simulate scenarios and store their stats")
    target = build.add_mutually_exclusive_group(required=True)
    target.add_argument("--scenario", help="a scenario TOML file")
    target.add_argument("--all", action="store_true", help="all storylines in scenarios/")
    build.add_argument("--season", action="store_true",
                       help="simulate and store the season history first, if missing")  # fmt: skip
    build.add_argument("--db", help="database URL (default: MATCHMIND_DB_URL)")
    args = parser.parse_args(argv)
    return _build(args)


if __name__ == "__main__":
    sys.exit(main())
