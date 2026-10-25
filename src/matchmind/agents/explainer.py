"""Explainer: turns one surfaced moment into an ``Insight`` with claims, refs, and advice.

Every number in an insight is a claim with the metric, value, unit, and ref (event id or
``metric:<name>@<period>:<t>``) it came from, read through the MCP stats tools. A reply
that breaks the shape (no event ids, no claims, a claim without a ref, a counterfactual
claim not read from ``get_counterfactual``) is sent back once with the problem; a second
bad reply raises ``ExplainerError``, and the pipeline falls back to a template (TASK-20).
The Verifier (TASK-18) then checks every claim against the stats store.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from agent_framework.exceptions import ChatClientException
from opentelemetry.trace import Tracer
from pydantic import BaseModel, ValidationError, model_validator

from matchmind.agents.context import moment_context
from matchmind.agents.runtime import (
    bad_reply,
    make_agent,
    problem_text,
    run_agent,
    tool_calls,
    trace_id,
)
from matchmind.schemas import AnalystDecision, Claim, Insight, Moment

PROMPT = "explainer.v1.md"
PROMPT_VERSION = "explainer.v1"
COUNTERFACTUAL_PREFIX = "counterfactual"
QUESTIONS = {
    "team": "What should they do?",
    "player": "What should they do?",
    "game": "What to watch next",
}


class ExplainerError(RuntimeError):
    """The Explainer could not produce a well-formed insight within its regeneration."""


class ExplainerReply(BaseModel):
    """What the model writes (``response_format``). Plain on purpose: the Foundry client
    parses the reply inside the request, so a failed check here would fail the call."""

    headline: str
    why: str
    recommendation: str
    claims: list[Claim]
    event_ids: list[str]
    confidence: Literal["high", "medium", "low"]


class ExplainerDraft(ExplainerReply):
    """A reply that passes the Explainer's checks."""

    @model_validator(mode="after")
    def _complete(self) -> ExplainerDraft:
        problems = []
        if not self.event_ids:
            problems.append("event_ids is empty: list the events the insight rests on")
        if not self.claims:
            problems.append("claims is empty: every number needs a claim")
        problems += [
            f"claim {i} ({c.metric}) has no ref"
            for i, c in enumerate(self.claims, 1)
            if not c.ref.strip()
        ]
        problems += [f"{name} is empty" for name in ("headline", "why", "recommendation")
                     if not getattr(self, name).strip()]  # fmt: skip
        if problems:
            raise ValueError("; ".join(problems))
        return self


def _message(decision: AnalystDecision, moment: Moment, names: Mapping[str, str]) -> str:
    question = QUESTIONS[decision.level]
    payload = {
        "decision": decision.model_dump(),
        "moment": moment_context(moment),
        "names": dict(names),
    }
    return (
        f"Explain moment {moment.moment_id} at the {decision.level} level. "
        f'The recommendation answers "{question}"\n{json.dumps(payload)}'
    )


def _counterfactuals_read(draft: ExplainerDraft, calls: list[tuple[str, dict[str, Any]]]) -> None:
    looked_up = {str(a.get("event_id")) for name, a in calls if name == "get_counterfactual"}
    unread = [
        c.ref for c in draft.claims
        if c.metric.startswith(COUNTERFACTUAL_PREFIX) and c.ref not in looked_up
    ]  # fmt: skip
    if unread:
        raise ValueError(
            f"counterfactual claims on {', '.join(unread)} were not read from "
            "get_counterfactual: call it with that event_id and quote its numbers"
        )


async def explain(
    decision: AnalystDecision,
    moment: Moment,
    client: Any,
    tools: Any,
    *,
    names: Mapping[str, str] | None = None,
    feedback: str | None = None,
    tracer: Tracer | None = None,
) -> Insight:
    """Explain one surfaced moment. Raises ``ExplainerError`` after one failed regeneration.
    ``names`` maps club and player ids to display names (``context.match_names``).
    ``feedback`` is the Verifier's failures on the previous insight, for a regeneration."""
    agent = make_agent(
        "explainer", PROMPT, ExplainerReply, tools, client=client, options={"temperature": 0.0}
    )
    message = _message(decision, moment, names or {})
    if feedback:
        message += (
            f"\n\nThe Verifier rejected your previous insight:\n{feedback}\n"
            "Fix every point. For a number that matches no verified stat, either delete it or "
            "call a stats tool and add its claim; never write it again without a claim."
        )
    problem = ""
    for attempt in (1, 2):
        text = message if attempt == 1 else (
            f"{message}\n\nYour last answer was rejected: {problem}. Fix it and answer again."
        )  # fmt: skip
        try:
            response = await run_agent(
                agent, text, moment_id=moment.moment_id, attempt=attempt, tracer=tracer
            )
        except ChatClientException as exc:
            problem = bad_reply(exc) or ""
            if not problem:
                raise  # a service error, not a bad reply: the pipeline's retry policy
            continue
        try:
            reply = response.value
            if not isinstance(reply, ExplainerReply):
                raise ValueError("the answer was not an insight in the requested JSON shape")
            draft = ExplainerDraft.model_validate(reply.model_dump())
            _counterfactuals_read(draft, tool_calls(response))
        except ValidationError as exc:
            problem = problem_text(exc)
            continue
        except ValueError as exc:
            problem = str(exc)
            continue
        return Insight(
            insight_id=f"{moment.moment_id}-ins",
            moment_id=moment.moment_id,
            match_id=moment.match_id,
            level=decision.level,
            headline=draft.headline,
            why=draft.why,
            recommendation=draft.recommendation,
            claims=draft.claims,
            event_ids=draft.event_ids,
            confidence=draft.confidence,
            verified=False,
            source="agent",
            trace_id=trace_id(response),
            prompt_version=PROMPT_VERSION,
        )
    raise ExplainerError(f"{moment.moment_id}: {problem}")
