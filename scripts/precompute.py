"""Precompute every match's insights, live lines, fan texts, and recap with the live model.

Usage:
    uv run python scripts/precompute.py --all
    uv run python scripts/precompute.py --match r01-chapinero-v-laureles --limit 1   # smoke

Resumable: anything already stored (insights, live lines, texts per language, recap) is
skipped, so an interrupted run can simply be started again. Throttled to ``--tpm`` (default
75% of the deployment's 200k quota). Writes `<data>/replays/<match>/replay_manifest.json`
and the per-match token and cost table in `docs/costs.md`. Needs the built database
(`matchmind build --all`), `az login`, and the Foundry settings in `.env`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from azure.identity.aio import DefaultAzureCredential
from mcp import Client

from matchmind.agents.orchestrator import ALL_LANGS, Deps, PipelineReport, run_match
from matchmind.agents.runtime import (
    PROMPT_DIR,
    TokenBucket,
    configure_tracing,
    make_chat_client,
    stats_tools,
)
from matchmind.agents.verifier import StatsFacts
from matchmind.config import get_settings
from matchmind.mcp_server.server import StatsService, build_mcp
from matchmind.store.blob import tracking_store
from matchmind.store.db import Repo

ROOT = Path(__file__).resolve().parents[1]
COSTS = ROOT / "docs" / "costs.md"
# gpt-4.1-mini list prices, USD per million tokens (Azure OpenAI global deployment).
PRICE_IN, PRICE_OUT = 0.40, 1.60


def cost_usd(tokens_in: int, tokens_out: int) -> float:
    return tokens_in / 1e6 * PRICE_IN + tokens_out / 1e6 * PRICE_OUT


def prompt_versions() -> dict[str, str]:
    """Each prompt file and a short hash of its text, so a replay names the prompts it used."""
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        for p in sorted(PROMPT_DIR.glob("*.md"))
    }


def write_manifest(repo: Repo, data_dir: Path, report: PipelineReport, deployment: str,
                   seconds: float) -> Path:  # fmt: skip
    meta = repo.get_match_meta(report.match_id)
    assert meta is not None
    path = data_dir / "replays" / report.match_id / "replay_manifest.json"
    before = json.loads(path.read_text()).get("run_seconds", 0.0) if path.exists() else 0.0
    runs = repo.list_match_runs(report.match_id)
    t_in, t_out = sum(r.tokens_in for r in runs), sum(r.tokens_out for r in runs)
    manifest = {
        "match_id": report.match_id,
        "scenario_id": meta.scenario_id,
        "seed": meta.seed,
        "engine_version": meta.engine_version,
        "model_deployment": deployment,
        "prompt_versions": prompt_versions(),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "insights": report.insights,
        "verified": report.verified,
        "templated": report.templated,
        "personalized": len(repo.list_personalized(report.match_id)),
        "recap": report.recap_source,
        "agent_runs": len([r for r in runs if r.status != "fallback"]),
        "fallbacks": len([r for r in runs if r.status == "fallback"]),
        "tokens_in": t_in,
        "tokens_out": t_out,
        "cost_usd": round(cost_usd(t_in, t_out), 4),
        "run_seconds": round(before + seconds, 1),  # wall time of every run so far
        "last_run_p95_latency_ms": report.p95_latency_ms,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def write_costs(data_dir: Path, deployment: str) -> None:
    rows = []
    for path in sorted((data_dir / "replays").glob("*/replay_manifest.json")):
        m = json.loads(path.read_text())
        rows.append(m)
    total_in = sum(m["tokens_in"] for m in rows)
    total_out = sum(m["tokens_out"] for m in rows)
    lines = [
        "# Costs",
        "",
        f"Precomputed with `scripts/precompute.py` on `{deployment}` (list price "
        f"${PRICE_IN:.2f} per million input tokens, ${PRICE_OUT:.2f} per million output). "
        "Tokens are the totals of every agent run stored for the match (`agent_runs`), "
        "retries and regenerations included; re-runs only add what was missing.",
        "",
        "| Match | Insights | Agent / template | Fan texts | Agent runs | Fallbacks "
        "| Tokens in | Tokens out | Cost (USD) | Run time |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]  # fmt: skip
    for m in rows:
        lines.append(
            f"| `{m['match_id']}` | {m['insights']} | {m['verified']} / {m['templated']} | "
            f"{m['personalized']} | {m['agent_runs']} | {m['fallbacks']} | {m['tokens_in']:,} | "
            f"{m['tokens_out']:,} | {m['cost_usd']:.2f} | {m['run_seconds'] / 60:.1f} min |"
        )
    if rows:
        lines += [
            f"| **Total ({len(rows)} matches)** | {sum(m['insights'] for m in rows)} | | "
            f"{sum(m['personalized'] for m in rows)} | {sum(m['agent_runs'] for m in rows)} | "
            f"{sum(m['fallbacks'] for m in rows)} | {total_in:,} | {total_out:,} | "
            f"**{cost_usd(total_in, total_out):.2f}** | |",
        ]
    COSTS.write_text("\n".join(lines) + "\n")


async def precompute(match_ids: list[str], args: argparse.Namespace) -> None:
    settings = get_settings()
    configure_tracing(settings)
    repo = Repo(settings.db_url)
    store = tracking_store(settings)
    stats = StatsService(repo, store)

    @cache
    def facts_for(match_id: str) -> StatsFacts:
        return StatsFacts(stats, match_id)

    limiter = TokenBucket(args.tpm)
    async with DefaultAzureCredential() as credential, Client(build_mcp(repo, store)) as mcp:
        client = make_chat_client(settings, credential)
        async with stats_tools(settings, session=mcp.session) as tools:
            deps = Deps(repo=repo, client=client, tools=tools, facts_for=facts_for,
                        langs=tuple(args.langs), limiter=limiter,
                        max_parallel=args.max_parallel)  # fmt: skip
            for match_id in match_ids:
                start = time.perf_counter()
                report = await run_match(match_id, deps, max_windows=args.max_windows,
                                         limit=args.limit)  # fmt: skip
                seconds = time.perf_counter() - start
                path = write_manifest(repo, settings.data_dir, report,
                                      settings.foundry_model_deployment, seconds)  # fmt: skip
                print(f"{match_id}: {report.insights} insights ({report.verified} agent, "
                      f"{report.templated} template), {report.personalized} new fan texts "
                      f"({report.personalized_templated} template), recap {report.recap_source}, "
                      f"{report.agent_runs} agent runs, p95 {report.p95_latency_ms / 1000:.1f} s, "
                      f"{seconds / 60:.1f} min → {path.name}")  # fmt: skip
    write_costs(settings.data_dir, settings.foundry_model_deployment)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--all", action="store_true", help="every match in the database")
    target.add_argument("--match", action="append", help="a match id (repeatable)")
    parser.add_argument("--tpm", type=int, default=150_000, help="tokens per minute to stay under")
    parser.add_argument("--langs", nargs="+", default=list(ALL_LANGS), choices=list(ALL_LANGS))
    parser.add_argument("--max-parallel", type=int, default=4, help="moments at once per window")
    parser.add_argument("--max-windows", type=int, default=2, help="windows at once per match")
    parser.add_argument("--limit", type=int, help="only the first N windows (smoke test)")
    parser.add_argument("--reset", action="store_true",
                        help="delete the matches' agent outputs first and start over")  # fmt: skip
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "agent_framework", "azure", "mcp"):
        logging.getLogger(noisy).setLevel(logging.ERROR)
    settings = get_settings()
    match_ids: list[str] = Repo(settings.db_url).list_matches() if args.all else args.match
    if args.reset:
        repo = Repo(settings.db_url)
        for match_id in match_ids:
            repo.clear_agent_outputs(match_id)
    asyncio.run(precompute(match_ids, args))


if __name__ == "__main__":
    main()
