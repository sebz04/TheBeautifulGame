"""Enforce the wiki rules (TASK-0): code changes come with a wiki update, pages stay short.

Usage:
  uv run python scripts/check_wiki.py                 # staged files (pre-commit hook)
  uv run python scripts/check_wiki.py --range A..B    # every commit in a range (CI)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

MAX_PAGE_LINES = 150
CODE_PREFIXES = ("src/", "web/src/")
WIKI_DIR = "wiki"


def check_files(changed: Iterable[str], page_lines: Mapping[str, int]) -> list[str]:
    changed = list(changed)
    errors: list[str] = []
    code = [f for f in changed if f.startswith(CODE_PREFIXES)]
    if code and not any(f.startswith(f"{WIKI_DIR}/") for f in changed):
        errors.append(f"code changed without a wiki/ update: {', '.join(code)}")
    errors += [
        f"{page} has {n} lines (max {MAX_PAGE_LINES})"
        for page, n in sorted(page_lines.items())
        if n > MAX_PAGE_LINES
    ]
    return errors


def wiki_page_lines(wiki_dir: Path) -> dict[str, int]:
    return {
        f"{WIKI_DIR}/{p.name}": len(p.read_text(encoding="utf-8").splitlines())
        for p in sorted(wiki_dir.glob("*.md"))
    }


def _git(repo: Path, *args: str) -> list[str]:
    out = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    return [line for line in out.splitlines() if line]


def check_range(rev_range: str, repo: Path) -> list[str]:
    errors: list[str] = []
    for sha in reversed(_git(repo, "rev-list", rev_range)):
        files = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha)
        short = _git(repo, "rev-parse", "--short", sha)[0]
        errors += [f"{short}: {e}" for e in check_files(files, page_lines={})]
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--range", dest="rev_range", help="git revision range, e.g. main..HEAD")
    args = parser.parse_args(argv)
    repo = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel")[0])

    if args.rev_range:
        errors = check_range(args.rev_range, repo)
    else:
        errors = check_files(_git(repo, "diff", "--cached", "--name-only"), page_lines={})
    errors += check_files([], wiki_page_lines(repo / WIKI_DIR))

    if errors:
        print("Wiki check failed (see wiki/conventions.md):\n  " + "\n  ".join(errors))
        return 1
    print("Wiki check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
