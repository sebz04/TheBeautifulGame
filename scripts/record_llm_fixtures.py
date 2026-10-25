"""Run the real agents on 3 moments and save every model reply as a fixture.

Usage: uv run python scripts/record_llm_fixtures.py [--scenario comeback_red_card]

For each moment: Tactical Analyst, then Explainer → Verifier with up to two regenerations
(``verify_loop``). Needs the built database (`matchmind build --all`), `az login`, and the
Foundry settings in `.env`. Writes `tests/fixtures/llm/<scenario>.json`: the model's
replies, each attempt's verdict, and the facts the Verifier looked up, so
`tests/agents/test_recorded.py` replays the whole loop without the model or the database.
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

from matchmind.agents import analyst, explainer, verifier
from matchmind.agents.runtime import configure_tracing, make_chat_client, stats_tools
from matchmind.agents.verifier import StatsFacts, verify_loop
from matchmind.config import get_settings
from matchmind.mcp_server.server import StatsService, build_mcp
from matchmind.schemas import Claim, Event, Insight, Moment, Verdict
from matchmind.store.blob import tracking_store
from matchmind.store.db import Repo

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "llm"
KINDS = ["red_card", "goal", "pressing_collapse", "formation_shift", "momentum_swing", "big_chance"]


class Recorder:
    """Chat middleware that keeps each model reply: which agent, its tool calls, its text."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []

    def middleware(self) -> Any:
        turns = self.turns

        @chat_middleware
        async def record(context: ChatContext, call_next: Any) -> None:
            await call_next()
            instructions = str((context.options or {}).get("instructions") or "")
            agent = instructions.split("\n", 1)[0].removeprefix("# ").split(" (")[0].lower()
            contents = [c for m in getattr(context.result, "messages", []) for c in m.contents]
            calls = [
                [c.name, json.loads(c.arguments) if isinstance(c.arguments, str) else c.arguments]
                for c in contents
                if c.type == "function_call"
            ]  # the model sends arguments as a JSON string
            text = "".join(c.text or "" for c in contents if c.type == "text")
            turns.append({"agent": agent, "tool_calls": calls, "text": text})

        return record

    def take(self) -> list[dict[str, Any]]:
        out = list(self.turns)
        self.turns.clear()
        return out


class RecordingFacts:
    """``StatsFacts`` that remembers every lookup, event, and third it hands out."""

    def __init__(self, inner: StatsFacts) -> None:
        self.inner = inner
        self.names, self.minutes = inner.names, inner.minutes
        self.scores, self.formations = inner.scores, inner.formations
        self.lookups: dict[str, float | None] = {}
        self.seen_events: dict[str, Any] = {}
        self.thirds: dict[str, str] = {}
        self.before_events: dict[str, list[dict[str, Any]]] = {}

    def lookup(self, claim: Claim) -> float | None:
        value = self.inner.lookup(claim)
        self.lookups[f"{claim.ref}|{claim.metric}|{claim.unit}"] = value
        return value

    def events(self, event_ids: list[str]) -> list[Event]:
        events = self.inner.events(event_ids)
        self.seen_events |= {e.event_id: e.model_dump() for e in events}
        return events

    def third(self, event: Event) -> str:
        self.thirds[event.event_id] = third = self.inner.third(event)
        return third

    def before(self, event: Event) -> list[Event]:
        events = self.inner.before(event)
        self.before_events[event.event_id] = [e.model_dump() for e in events]
        return events

    def dump(self) -> dict[str, Any]:
        return {
            "names": dict(self.names),
            "minutes": sorted(self.minutes),
            "scores": sorted(self.scores),
            "formations": sorted(self.formations),
            "lookups": self.lookups,
            "events": self.seen_events,
            "thirds": self.thirds,
            "before": self.before_events,
        }


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
    store = tracking_store(settings)
    facts = RecordingFacts(StatsFacts(StatsService(repo, store), match_id))
    moments = pick(repo.list_moments(match_id))
    recorder = Recorder()
    entries = []
    async with DefaultAzureCredential() as credential, Client(build_mcp(repo, store)) as mcp:
        client = make_chat_client(settings, credential, middleware=[recorder.middleware()])
        async with stats_tools(settings, session=mcp.session) as tools:
            for m in moments:
                start = time.perf_counter()
                decisions = await analyst.analyze([m], client, tools, names=facts.names)
                entry: dict[str, Any] = {
                    "moment": m.model_dump(),
                    "analyst_turns": recorder.take(),
                    "decision": decisions[0].model_dump() if decisions else None,
                    "attempts": [],
                    "final": None,
                }

                def attempt(
                    insight: Insight, verdict: Verdict, entry: dict[str, Any] = entry
                ) -> None:
                    entry["attempts"].append({
                        "insight": insight.model_dump(),
                        "verdict": verdict.model_dump(),
                        "turns": recorder.take(),
                    })  # fmt: skip

                if decisions:
                    final = await verify_loop(
                        decisions[0], m, client, tools, facts, on_attempt=attempt
                    )
                    entry["final"] = final.model_dump() if final else None
                entry["seconds"] = round(time.perf_counter() - start, 1)
                entries.append(entry)
                outcome = entry["final"]["headline"] if entry["final"] else "→ template"
                print(f"{m.moment_id} ({m.kind}): {len(entry['attempts'])} attempt(s): {outcome} "
                      f"[{entry['seconds']} s]")  # fmt: skip
                for a in entry["attempts"]:
                    for f in a["verdict"]["failures"]:
                        print("   ✗", f)

    path = FIXTURE_DIR / f"{scenario}.json"
    path.write_text(json.dumps({
        "recorded": date.today().isoformat(),
        "deployment": settings.foundry_model_deployment,
        "prompts": [analyst.PROMPT, explainer.PROMPT, verifier.PROMPT],
        "match_id": match_id,
        "facts": facts.dump(),
        "entries": entries,
    }, indent=1, ensure_ascii=False) + "\n")  # fmt: skip
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="comeback_red_card")
    print("wrote", asyncio.run(record(parser.parse_args().scenario)))


if __name__ == "__main__":
    main()
