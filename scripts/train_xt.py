"""Train the xT grid on synthetic matches and save it (TASK-7; retrained in TASK-10).

Usage:
  uv run python scripts/train_xt.py --seeds 200 --level 1
Writes data/models/xt_grid.npy plus xt_grid.json (provenance). Matches are simulated in
parallel; only their normalized events come back to the main process.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from realism_report import fixture_for_seed

from matchmind.engine.lineup import ENGINE_VERSION, match_meta
from matchmind.engine.simulate import simulate_match
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.schemas import Event
from matchmind.stats.xt import DEFAULT_GRID_PATH, normalize_events, train_xt


def _events_for_seed(args: tuple[int, int]) -> list[Event]:
    seed, level = args
    league = build_league()
    meta = match_meta(league, fixture_for_seed(build_fixtures(league, seed=2026), seed), seed)
    data = simulate_match(meta, level=level, tracking=False)  # type: ignore[arg-type]
    return normalize_events(data)


def write_grid(grid: np.ndarray, out: Path, provenance: dict[str, Any]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out, grid)
    meta = {**provenance, "shape": list(grid.shape)}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=200)
    parser.add_argument("--level", type=int, choices=[1, 3], default=1)
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--out", type=Path, default=DEFAULT_GRID_PATH)
    args = parser.parse_args(argv)

    start = time.perf_counter()
    events: list[Event] = []
    jobs = [(seed, args.level) for seed in range(1, args.seeds + 1)]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for done, match_events in enumerate(pool.map(_events_for_seed, jobs), start=1):
            events += match_events
            if done % 20 == 0 or done == len(jobs):
                print(f"{done}/{len(jobs)} matches, {time.perf_counter() - start:.0f}s",
                      file=sys.stderr)  # fmt: skip
    grid = train_xt(events)
    provenance = {"level": args.level, "seeds": args.seeds, "events": len(events),
                  "engine_version": ENGINE_VERSION}  # fmt: skip
    write_grid(grid, args.out, provenance)
    print(f"saved {args.out} ({len(events)} events)")
    print(np.array2string(grid, precision=3, max_line_width=140))
    return 0


if __name__ == "__main__":
    sys.exit(main())
