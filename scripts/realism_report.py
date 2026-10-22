"""Simulate many matches and check them against the realism ranges (TASK-5).

Usage:
  uv run python scripts/realism_report.py --level 1 --seeds 20
  uv run python scripts/realism_report.py --level 1 --seeds 20 --out docs/realism.md
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Iterator
from pathlib import Path

from matchmind.engine.lineup import match_meta
from matchmind.engine.simulate import simulate_match
from matchmind.engine.validate import RealismReport, validate_many
from matchmind.league.fixtures import Fixture, build_fixtures
from matchmind.league.league import build_league
from matchmind.schemas import MatchData


def fixture_for_seed(fixtures: list[Fixture], seed: int) -> Fixture:
    """Spread seeds across rounds and clubs (19 is coprime with 380)."""
    return fixtures[((seed - 1) * 19) % len(fixtures)]


def render_markdown(report: RealismReport, level: int, seeds: int) -> str:
    passed = sum(c.ok for c in report.checks)
    lines = [
        f"### Level {level}, {seeds} seeds",
        "",
        f"{passed}/{len(report.checks)} checks pass. Values are means over team-matches "
        '(goals: per match). "In range" is the share of team-matches inside the range.',
        "",
        "| Check | Mean | Range | In range | Result |",
        "|---|---|---|---|---|",
    ]
    for c in report.checks:
        share = "–" if c.in_range_share is None else f"{c.in_range_share:.0%}"
        result = "pass" if c.ok else "**FAIL**"
        lines.append(f"| {c.name} | {c.value:.2f} | {c.lo:g}–{c.hi:g} | {share} | {result} |")
    return "\n".join(lines) + "\n"


def _matches(level: int, seeds: int) -> Iterator[MatchData]:
    league = build_league()
    fixtures = build_fixtures(league, seed=2026)
    for seed in range(1, seeds + 1):
        start = time.perf_counter()
        meta = match_meta(league, fixture_for_seed(fixtures, seed), seed=seed)
        data = simulate_match(meta, level=level)  # type: ignore[arg-type]
        print(f"seed {seed}: {meta.match_id} in {time.perf_counter() - start:.1f}s",
              file=sys.stderr)  # fmt: skip
        yield data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", type=int, choices=[1, 3], default=1)
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--out", type=Path, help="write the Markdown table here")
    args = parser.parse_args(argv)
    report = validate_many(_matches(args.level, args.seeds))
    md = render_markdown(report, args.level, args.seeds)
    print(md)
    if args.out:
        args.out.write_text(md)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
