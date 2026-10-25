"""Run the real Analyst and Explainer on 3 moments and save every model reply as a fixture.

Usage: uv run python scripts/record_llm_fixtures.py [--scenario comeback_red_card]

Needs the built database (`matchmind build --all`), `az login`, and Foundry settings in
`.env`. Writes `tests/fixtures/llm/<scenario>.json`, which `tests/agents/test_recorded.py`
replays without calling the model.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from agent_framework import ChatContext, chat_middleware
from azure.identity.aio import DefaultAzureCredential
from mcp import Client

from matchmind.agents import analyst, explainer
from matchmind.agents.context import match_names
from matchmind.agents.explainer import ExplainerError
from matchmind.agents.runtime import configure_tracing, make_chat_client, stats_tools
from matchmind.config import get_settings
from matchmind.mcp_server.server import build_mcp
from matchmind.schemas import Moment
from matchmind.store.blob import tracking_store
from matchmind.store.db import Repo

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "llm"
KINDS = ["red_card", "goal", "pressing_collapse", "formation_shift", "momentum_swing", "big_chance"]


class Recorder:
    """Chat middleware that keeps each model reply: its tool calls and its text."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []

    def middleware(self) -> Any:
        turns = self.turns

        @chat_middleware
        async def record(context: ChatContext, call_next: Any) -> None:
            await call_next()
            result = context.result
            contents = [c for m in getattr(result, "messages", []) for c in m.contents]
            calls = [
                [c.name, json.loads(c.arguments) if isinstance(c.arguments, str) else c.arguments]
                for c in contents
                if c.type == "function_call"
            ]  # the model sends arguments as a JSON string
            text = "".join(c.text or "" for c in contents if c.type == "text")
            turns.append({"tool_calls": calls, "text": text})

        return record

    def take(self) -> list[dict[str, Any]]:
        out = list(self.turns)
        self.turns.clear()
        return out


def pick(moments: list[Moment], n: int = 3) -> list[Moment]:
    chosen: list[Moment] = []
    for kind in KINDS:
        chosen += [m for m in moments if m.kind == kind][:1]
    return chosen[:n]


async def record(scenario: str) -> Path:
    settings = get_settings()
    configure_tracing(settings)
    repo = Repo(settings.db_url)
    match_id = next(
        m
        for m in repo.list_matches()
        if (meta := repo.get_match_meta(m)) and meta.scenario_id == scenario
    )
    moments = pick(repo.list_moments(match_id))
    meta = repo.get_match_meta(match_id)
    assert meta is not None
    names = match_names(meta)
    recorder = Recorder()
    entries = []
    server = build_mcp(repo, tracking_store(settings))
    async with DefaultAzureCredential() as credential, Client(server) as mcp_client:
        client = make_chat_client(settings, credential, middleware=[recorder.middleware()])
        async with stats_tools(settings, session=mcp_client.session) as tools:
            for m in moments:
                start = time.perf_counter()
                decisions = await analyst.analyze([m], client, tools, names=names)
                entry: dict[str, Any] = {
                    "moment": m.model_dump(),
                    "analyst_turns": recorder.take(),
                    "decision": decisions[0].model_dump() if decisions else None,
                    "explainer_turns": [],
                    "insight": None,
                    "error": None,
                }
                if decisions:
                    try:
                        insight = await explainer.explain(
                            decisions[0], m, client, tools, names=names
                        )
                        entry["insight"] = insight.model_dump()
                    except ExplainerError as exc:
                        entry["error"] = str(exc)
                    entry["explainer_turns"] = recorder.take()
                entry["seconds"] = round(time.perf_counter() - start, 1)
                entries.append(entry)
                headline = (entry["insight"] or {}).get(
                    "headline", entry["error"] or "not surfaced"
                )
                print(f"{m.moment_id} ({m.kind}): {headline} [{entry['seconds']} s]")

    path = FIXTURE_DIR / f"{scenario}.json"
    path.write_text(json.dumps({
        "recorded": date.today().isoformat(),
        "deployment": settings.foundry_model_deployment,
        "prompts": [analyst.PROMPT, explainer.PROMPT],
        "match_id": match_id,
        "entries": entries,
    }, indent=1, ensure_ascii=False) + "\n")  # fmt: skip
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="comeback_red_card")
    print("wrote", asyncio.run(record(parser.parse_args().scenario)))


if __name__ == "__main__":
    main()
