"""Tactical Analyst: decides which detected moments are worth explaining, and how.

It sees a batch of moments (one per 5 match-minutes), looks each one up through the MCP
stats tools, and returns an ``AnalystDecision`` per moment. A moment it surfaces without
looking up any of its stats is sent back once; if it still isn't looked up, it's dropped.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from itertools import groupby
from typing import Any

from agent_framework.exceptions import ChatClientException
from pydantic import BaseModel

from matchmind.agents.context import moment_context
from matchmind.agents.runtime import bad_reply, make_agent, run_agent, tool_calls
from matchmind.clock import minute_label
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


def _looked_up(m: Moment, calls: Calls) -> bool:
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


def _message(moments: Sequence[Moment], names: Mapping[str, str]) -> str:
    first, last = moments[0], moments[-1]
    header = (
        f"Match {first.match_id}, {minute_label(first.period, first.t_start)} to "
        f"{minute_label(last.period, last.t_end)}: decide which moments to explain."
    )
    payload = {
        "match_id": first.match_id,
        "names": dict(names),
        "moments": [
            {k: v for k, v in moment_context(m).items() if k != "match_id"} for m in moments
        ],
    }
    return f"{header}\n{json.dumps(payload)}"


async def analyze(
    moments: Sequence[Moment],
    client: Any,
    tools: Any,
    *,
    names: Mapping[str, str] | None = None,
) -> list[AnalystDecision]:
    """Decide which of ``moments`` (one batch) to explain. Returns only surfaced moments,
    highest priority first, each one looked up through at least one stats tool.
    ``names`` maps club and player ids to display names (``context.match_names``)."""
    if not moments:
        return []
    agent = make_agent("analyst", PROMPT, AnalystBatch, tools, client=client)
    by_id = {m.moment_id: m for m in moments}
    span_id = ",".join(by_id)
    message = _message(moments, names or {})

    decisions, calls, problem = await _attempt(agent, message, by_id, span_id, 1)
    skipped = [
        d.moment_id for d in decisions if d.surface and not _looked_up(by_id[d.moment_id], calls)
    ]
    if problem or skipped:
        feedback = (
            f"Your last answer was rejected: {problem}. Answer again in the requested shape."
            if problem
            else f"You surfaced {', '.join(skipped)} without looking up its stats. "
            "Call get_moment (or another stats tool) for every moment you surface."
        )
        decisions, more_calls, problem = await _attempt(
            agent, f"{message}\n\n{feedback}", by_id, span_id, 2
        )
        calls += more_calls

    surfaced = [d for d in decisions if d.surface and _looked_up(by_id[d.moment_id], calls)]
    return sorted(surfaced, key=lambda d: -d.priority)


Calls = list[tuple[str, dict[str, Any]]]


async def _attempt(
    agent: Any, text: str, by_id: dict[str, Moment], span_id: str, attempt: int
) -> tuple[list[AnalystDecision], Calls, str]:
    """One run: the known decisions, the tool calls made, and why the reply was bad (or "").

    A reply that doesn't fit ``AnalystBatch`` yields no decisions; service errors
    (timeouts, 429s) are raised for the pipeline's retry policy.
    """
    try:
        response = await run_agent(agent, text, moment_id=span_id, attempt=attempt)
    except ChatClientException as exc:
        problem = bad_reply(exc)
        if problem is None:
            raise
        return [], [], problem
    batch = response.value
    if not isinstance(batch, AnalystBatch):
        return [], tool_calls(response), "the answer was not JSON in the requested shape"
    return _known(batch.decisions, by_id), tool_calls(response), ""


def _known(decisions: list[AnalystDecision], by_id: dict[str, Moment]) -> list[AnalystDecision]:
    """Decisions about moments in the batch, the first one per moment."""
    seen: set[str] = set()
    out = []
    for d in decisions:
        if d.moment_id in by_id and d.moment_id not in seen:
            seen.add(d.moment_id)
            out.append(d)
    return out
