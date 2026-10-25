"""Fail if any runtime dependency has a license outside the allowlist (Constitution III).

Usage: uv run python scripts/check_licenses.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from packaging.markers import Marker

ALLOWED_PATTERNS = [
    r"\bmit\b",
    r"\b0?bsd\b",
    r"\bapache\b",
    r"python software foundation|\bpsf\b",
    r"\bisc\b",
    r"mpl[ -]?2\.0|mozilla public license 2\.0",
    r"\bzlib\b",
    r"\bcc0\b",  # public domain dedication
]


def _single_allowed(text: str) -> bool:
    return any(re.search(p, text.lower()) for p in ALLOWED_PATTERNS)


def is_allowed(license_text: str) -> bool:
    """True if the license (classifier list or SPDX expression) is permissive.

    `;` and `OR` separate alternatives (one must be allowed); `AND` joins
    terms that must all be allowed.
    """
    cleaned = license_text.replace("(", " ").replace(")", " ")
    alternatives = re.split(r";|\s+OR\s+", cleaned)
    return any(
        all(_single_allowed(part) for part in re.split(r"\s+AND\s+", alt) if part.strip())
        and alt.strip() != ""
        for alt in alternatives
    )


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def find_violations(packages: list[dict[str, str]], runtime: set[str]) -> list[str]:
    runtime_norm = {_normalize(n) for n in runtime}
    reported = {_normalize(p["Name"]) for p in packages}
    missing = [
        f"{n}: not found in license report"
        for n in sorted(runtime)
        if _normalize(n) not in reported
    ]
    return missing + [
        f"{p['Name']}: {p['License']}"
        for p in packages
        if _normalize(p["Name"]) in runtime_norm and not is_allowed(p["License"])
    ]


def runtime_packages() -> set[str]:
    out = subprocess.run(
        [
            "uv",
            "export",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--format",
            "requirements-txt",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return parse_export(out)


def parse_export(text: str, environment: dict[str, str] | None = None) -> set[str]:
    """Package names from `uv export` output, skipping those whose environment marker
    does not apply here (e.g. `pywin32 ; sys_platform == 'win32'` on macOS or Linux)."""
    names = set()
    for line in text.splitlines():
        if not line or line.startswith(("#", " ")):
            continue
        requirement, _, marker = line.partition(";")
        if marker.strip() and not Marker(marker.strip()).evaluate(environment):
            continue
        names.add(re.split(r"[=<>\[ ]", requirement.strip(), maxsplit=1)[0])
    return names


def installed_licenses() -> list[dict[str, str]]:
    out = subprocess.run(
        ["pip-licenses", "--format=json", "--from=mixed"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return list(json.loads(out))


def main() -> int:
    runtime = runtime_packages()
    violations = find_violations(installed_licenses(), runtime)
    if violations:
        print("Disallowed runtime licenses:\n  " + "\n  ".join(violations))
        return 1
    print(f"License check passed for {len(runtime)} runtime packages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
