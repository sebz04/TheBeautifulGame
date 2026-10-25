"""Replay replies recorded from the live Foundry deployment (scripts/record_llm_fixtures.py).

These pin what the real model sends back, and how the Verifier judged it, so a change to
our parsing, checks, or output models that would break against the live model fails here,
without calling the model or needing the built database.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from conftest import StatsStub

from matchmind.agents.analyst import analyze
from matchmind.agents.runtime import FakeCall, FakeChatClient, FakeReply, tool_call
from matchmind.agents.verifier import DictFacts, verify_loop
from matchmind.schemas import AnalystDecision, Insight, Moment, Verdict

FIXTURE = Path(__file__).parents[1] / "fixtures" / "llm" / "comeback_red_card.json"
RECORDING: dict[str, Any] = json.loads(FIXTURE.read_text())
ENTRIES: list[dict[str, Any]] = RECORDING["entries"]


def _replay(turns: list[dict[str, Any]]) -> FakeChatClient:
    """A fake client that sends back the recorded turns in order."""
    queue: Iterator[dict[str, Any]] = iter(turns)

    def reply(call: FakeCall) -> FakeReply:
        turn = next(queue)
        if turn["tool_calls"]:
            return [tool_call(name, **args) for name, args in turn["tool_calls"]]
        return str(turn["text"])

    return FakeChatClient(reply)


def test_three_moments_were_recorded_and_verified() -> None:
    assert len(ENTRIES) == 3
    assert len({e["moment"]["kind"] for e in ENTRIES}) == 3
    assert all(e["final"] and e["final"]["verified"] for e in ENTRIES)


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["moment"]["kind"])
async def test_recorded_analyst_replay(entry: dict[str, Any], stats: StatsStub) -> None:
    m = Moment(**entry["moment"])
    decisions = await analyze([m], _replay(entry["analyst_turns"]), stats.tools())
    assert decisions == [AnalystDecision(**entry["decision"])]


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["moment"]["kind"])
async def test_recorded_verify_loop_replay(entry: dict[str, Any], stats: StatsStub) -> None:
    """Explainer → Verifier with the recorded replies: same drafts, same verdicts."""
    m, decision = Moment(**entry["moment"]), AnalystDecision(**entry["decision"])
    turns = [t for a in entry["attempts"] for t in a["turns"]]
    seen: list[tuple[Insight, Verdict]] = []
    final = await verify_loop(
        decision, m, _replay(turns), stats.tools(), DictFacts(RECORDING["facts"]),
        on_attempt=lambda i, v: seen.append((i, v)),
    )  # fmt: skip
    assert [v.model_dump() for _, v in seen] == [a["verdict"] for a in entry["attempts"]]
    assert [i.headline for i, _ in seen] == [a["insight"]["headline"] for a in entry["attempts"]]
    assert final is not None and final.headline == entry["final"]["headline"] and final.verified


def test_recorded_insights_use_names_not_ids() -> None:
    for e in ENTRIES:
        text = " ".join(e["final"][k] for k in ("headline", "why", "recommendation"))
        ids = [e["moment"]["player_id"], e["moment"]["team_id"]]
        assert not any(i and i in text for i in ids), text


def test_recorded_claims_are_scoped() -> None:
    for e in ENTRIES:
        for c in e["final"]["claims"]:
            assert c["ref"].startswith(("metric:", "deviation:")) is ("/" in c["ref"])
