"""Evaluate the Verifier on its golden set with the live Foundry deployment.

Usage: uv run python scripts/run_foundry_eval.py [--runs 1]

Runs the full ``verify`` (the number check, then the Verifier agent on gpt-4.1-mini in
Foundry) on every line of `evals/verifier_golden.jsonl`. A planted error counts as caught
when the verdict fails; a correct insight that fails is a false alarm. Prints and writes
precision, recall (overall and per stage), and every miss to `docs/evals.md`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from azure.identity.aio import DefaultAzureCredential

from matchmind.agents.runtime import configure_tracing, make_chat_client
from matchmind.agents.verifier import PROMPT, DictFacts, verify
from matchmind.config import get_settings
from matchmind.schemas import Insight

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "evals" / "verifier_golden.jsonl"
REPORT = ROOT / "docs" / "evals.md"
TARGET_RECALL = 0.95
NOTES_MARKER = "<!-- notes: kept when this report is regenerated -->"


async def run(runs: int) -> list[dict[str, Any]]:
    settings = get_settings()
    configure_tracing(settings)
    lines = [json.loads(x) for x in GOLDEN.read_text().splitlines()]
    results = []
    async with DefaultAzureCredential() as credential:
        client = make_chat_client(settings, credential)
        for run_no in range(1, runs + 1):
            for line in lines:
                start = time.perf_counter()
                verdict = await verify(
                    Insight(**line["insight"]), line["lang"], line["text"],
                    DictFacts(line["facts"]), client,
                )  # fmt: skip
                results.append({
                    "run": run_no, "id": line["id"], "kind": line["kind"],
                    "stage": line["stage"], "lang": line["lang"], "flagged": not verdict.ok,
                    "failures": verdict.failures,
                    "ms": round((time.perf_counter() - start) * 1000),
                })  # fmt: skip
                r = results[-1]
                ok = r["flagged"] == (r["stage"] is not None)
                print(f"{'✓' if ok else '✗'} {r['id']} {r['kind']:<18} {r['ms']:>6} ms "
                      f"{'; '.join(r['failures'])[:110]}")  # fmt: skip
    return results


def _rate(n: int, d: int) -> str:
    return f"{n}/{d} = {n / d:.2f}" if d else "n/a"


def report(results: list[dict[str, Any]], runs: int, deployment: str) -> str:
    planted = [r for r in results if r["stage"]]
    correct = [r for r in results if not r["stage"]]
    caught = sum(r["flagged"] for r in planted)
    alarms = sum(r["flagged"] for r in correct)
    recall = caught / len(planted)
    by_stage = {
        s: _rate(sum(r["flagged"] for r in planted if r["stage"] == s),
                 sum(r["stage"] == s for r in planted))
        for s in ("numbers", "wording")
    }  # fmt: skip
    model_ms = sorted(r["ms"] for r in results if not r["stage"] or r["stage"] == "wording")
    misses = [r for r in planted if not r["flagged"]]
    alarm_rows = [r for r in correct if r["flagged"]]
    lines = [
        "# Evaluations",
        "",
        "## Verifier (TASK-18.2)",
        "",
        f"Golden set: `evals/verifier_golden.jsonl`, 40 insights written by code from three built "
        f"matches (`scripts/build_verifier_golden.py`): 20 correct (all 5 languages) and 20 with "
        f"one planted error each, 12 for the number check and 8 for the wording check. Run "
        f"`scripts/run_foundry_eval.py`: the full `verify` with `{deployment}` in Foundry and "
        f"prompt `{PROMPT}`, {runs} run(s), {date.today().isoformat()}.",
        "",
        "| Measure | Result | Target |",
        "|---|---|---|",
        f"| Recall on planted errors | {_rate(caught, len(planted))} | ≥ {TARGET_RECALL} "
        f"{'✅' if recall >= TARGET_RECALL else '❌'} |",
        f"| … caught by the number check | {by_stage['numbers']} | 1.00 (deterministic) |",
        f"| … caught by the Verifier agent | {by_stage['wording']} | |",
        f"| Precision | {_rate(caught, caught + alarms)} | |",
        f"| False alarms on correct insights | {_rate(alarms, len(correct))} | |",
        f"| Median time per model check | {model_ms[len(model_ms) // 2]} ms | |",
        "",
    ]
    if misses:
        lines += ["**Missed errors:**", ""]
        lines += [f"- `{r['id']}` {r['kind']} (run {r['run']})" for r in misses]
        lines.append("")
    if alarm_rows:
        lines += ["**False alarms:**", ""]
        lines += [f"- `{r['id']}` ({r['lang']}, run {r['run']}): {'; '.join(r['failures'])}"
                  for r in alarm_rows]  # fmt: skip
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    runs = parser.parse_args().runs
    results = asyncio.run(run(runs))
    text = report(results, runs, get_settings().foundry_model_deployment)
    old = REPORT.read_text() if REPORT.exists() else ""
    notes = old[old.index(NOTES_MARKER) :] if NOTES_MARKER in old else NOTES_MARKER + "\n"
    REPORT.write_text(text + "\n" + notes)
    print("\n" + text)


if __name__ == "__main__":
    main()
