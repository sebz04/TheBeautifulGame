"""Replay replies recorded from the live Foundry deployment (scripts/record_llm_fixtures.py).

These pin what the real model sends back, so a change to our parsing, checks, or output
models that would break against the live model fails here, without calling it.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from conftest import StatsStub

from matchmind.agents.analyst import analyze
from matchmind.agents.explainer import explain
from matchmind.agents.runtime import FakeCall, FakeChatClient, FakeReply, tool_call
from matchmind.schemas import AnalystDecision, Moment

FIXTURE = Path(__file__).parents[1] / "fixtures" / "llm" / "comeback_red_card.json"
ENTRIES: list[dict[str, Any]] = json.loads(FIXTURE.read_text())["entries"]


def _replay(turns: list[dict[str, Any]]) -> FakeChatClient:
    """A fake client that sends back the recorded turns in order."""
    queue: Iterator[dict[str, Any]] = iter(turns)

    def reply(call: FakeCall) -> FakeReply:
        turn = next(queue)
        if turn["tool_calls"]:
            return [tool_call(name, **args) for name, args in turn["tool_calls"]]
        return str(turn["text"])

    return FakeChatClient(reply)


def test_three_moments_were_recorded() -> None:
    assert len(ENTRIES) == 3
    assert len({e["moment"]["kind"] for e in ENTRIES}) == 3
    assert all(e["insight"] and not e["error"] for e in ENTRIES)


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["moment"]["kind"])
async def test_recorded_analyst_replay(entry: dict[str, Any], stats: StatsStub) -> None:
    m = Moment(**entry["moment"])
    decisions = await analyze([m], _replay(entry["analyst_turns"]), stats.tools())
    assert decisions == [AnalystDecision(**entry["decision"])]


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["moment"]["kind"])
async def test_recorded_explainer_replay(entry: dict[str, Any], stats: StatsStub) -> None:
    m, decision = Moment(**entry["moment"]), AnalystDecision(**entry["decision"])
    insight = await explain(decision, m, _replay(entry["explainer_turns"]), stats.tools())
    recorded = entry["insight"]
    assert insight.headline == recorded["headline"]
    assert insight.claims and all(c.ref for c in insight.claims)
    assert insight.event_ids == recorded["event_ids"]


def test_recorded_insights_use_names_not_ids() -> None:
    for e in ENTRIES:
        text = " ".join(e["insight"][k] for k in ("headline", "why", "recommendation"))
        ids = [e["moment"]["player_id"], e["moment"]["team_id"]]
        assert not any(i and i in text for i in ids), text
