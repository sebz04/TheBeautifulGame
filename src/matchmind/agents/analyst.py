"""Tactical Analyst: decides which detected moments are worth explaining, and how.

It sees a batch of moments (one per 5 match-minutes), looks each one up through the MCP
stats tools, and returns an ``AnalystDecision`` per moment. A moment it surfaces without
looking up any of its stats is sent back once; if it still isn't looked up, it's dropped.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from itertools import groupby
from typing import Any

from agent_framework import AgentResponse
from pydantic import BaseModel

from matchmind.agents.runtime import make_agent, run_agent
from matchmind.schemas import AnalystDecision, Moment

PROMPT = "analyst.v1.md"
# A time-scoped tool call within this many seconds of a moment counts as looking it up.
WINDOW_SLACK_S = 60.0


class AnalystBatch(BaseModel):
    decisions: list[AnalystDecision]


def batches(moments: Sequence[Moment], minutes: int = 5) -> list[list[Moment]]:
    """Moments grouped into ``minutes``-long windows of match time, per period, in order."""
    ordered = sorted(moments, key=lambda m: (m.period, m.t_start))
    return [
        list(group)
        for _, group in groupby(ordered, key=lambda m: (m.period, int(m.t_start // (60 * minutes))))
    ]


def _tool_calls(response: AgentResponse[Any]) -> list[tuple[str, dict[str, Any]]]:
    calls = []
    for message in response.messages:
        for c in message.contents:
            if c.type == "function_call":
                args = c.arguments
                if isinstance(args, str):
                    args = json.loads(args or "{}")
                calls.append((str(c.name), dict(args or {})))
    return calls


def _looked_up(m: Moment, calls: list[tuple[str, dict[str, Any]]]) -> bool:
    """True if some tool call was about this moment: its id, one of its events, or its time."""
    lo, hi = m.t_start - WINDOW_SLACK_S, m.t_end + WINDOW_SLACK_S
    for _, args in calls:
        if args.get("moment_id") == m.moment_id or args.get("event_id") in m.event_ids:
            return True
        if args.get("match_id") not in (None, m.match_id) or args.get("period") != m.period:
            continue
        if "t" in args and lo <= float(args["t"]) <= hi:
            return True
        if "t_from" in args and float(args["t_from"]) <= hi and float(args.get("t_to", hi)) >= lo:
            return True
    return False


def _message(moments: Sequence[Moment]) -> str:
    first, last = moments[0], moments[-1]
    header = (
        f"Match {first.match_id}, period {first.period}, "
        f"{first.t_start / 60:.0f}' to {last.t_end / 60:.0f}': decide which moments to explain."
    )
    payload = {
        "match_id": first.match_id,
        "moments": [m.model_dump(exclude={"match_id"}) for m in moments],
    }
    return f"{header}\n{json.dumps(payload)}"


async def analyze(moments: Sequence[Moment], client: Any, tools: Any) -> list[AnalystDecision]:
    """Decide which of ``moments`` (one batch) to explain. Returns only surfaced moments,
    highest priority first, each one looked up through at least one stats tool."""
    if not moments:
        return []
    agent = make_agent("analyst", PROMPT, AnalystBatch, tools, client=client)
    by_id = {m.moment_id: m for m in moments}
    span_id = ",".join(by_id)
    message = _message(moments)

    response = await run_agent(agent, message, moment_id=span_id, attempt=1)
    calls = _tool_calls(response)
    decisions = _known(_decisions(response), by_id)
    skipped = [
        d.moment_id for d in decisions if d.surface and not _looked_up(by_id[d.moment_id], calls)
    ]
    if skipped:
        retry = (
            f"{message}\n\nYou surfaced {', '.join(skipped)} without looking up its stats. "
            "Call get_moment (or another stats tool) for every moment you surface."
        )
        response = await run_agent(agent, retry, moment_id=span_id, attempt=2)
        calls += _tool_calls(response)
        decisions = _known(_decisions(response), by_id)

    surfaced = [d for d in decisions if d.surface and _looked_up(by_id[d.moment_id], calls)]
    return sorted(surfaced, key=lambda d: -d.priority)


def _decisions(response: AgentResponse[Any]) -> list[AnalystDecision]:
    batch = response.value
    return batch.decisions if isinstance(batch, AnalystBatch) else []


def _known(decisions: list[AnalystDecision], by_id: dict[str, Moment]) -> list[AnalystDecision]:
    """Decisions about moments in the batch, the first one per moment."""
    seen: set[str] = set()
    out = []
    for d in decisions:
        if d.moment_id in by_id and d.moment_id not in seen:
            seen.add(d.moment_id)
            out.append(d)
    return out
