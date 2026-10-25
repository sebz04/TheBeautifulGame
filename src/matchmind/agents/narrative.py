"""Narrative: one-line live updates and the full-time recap, from verified insights.

The model only rewrites what is already verified. A live line may quote the insight's
claims and season milestones (computed by code); a recap cites its key numbers by ref, and
code maps each ref back to a verified claim, so the model never supplies a value. Every
number is checked (``numbers.check_text``); a bad reply gets one regeneration with the
problems, then a deterministic fallback: the insight's headline, or a template recap.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_framework.exceptions import ChatClientException
from pydantic import BaseModel

from matchmind.agents.numbers import check_text, extract_numbers
from matchmind.agents.runtime import bad_reply, make_agent, run_agent
from matchmind.agents.templates import LABELS, format_value
from matchmind.clock import match_minute, minute_label
from matchmind.schemas import Claim, Insight, Recap

PROMPT = "narrative.v1.md"
MAX_LINE = 140
MAX_KEY_NUMBERS = 3
OPTIONS = {"temperature": 0.0}


class LineReply(BaseModel):
    text: str


class RecapReply(BaseModel):
    title: str
    paragraphs: list[str]
    key_refs: list[str]


@dataclass
class RecapContext:
    """What the recap may say besides the insights: the result, goals, red cards, and
    milestones, all from the stats store (``recap_context``)."""

    match_id: str
    home: str
    away: str
    score: tuple[int, int]
    goals: list[tuple[str, str, str]]  # (minute label, player, team)
    cards: list[tuple[str, str, str]]  # red cards, same shape
    milestones: list[str]
    minutes: set[int] = field(default_factory=set)
    scores: set[tuple[int, int]] = field(default_factory=set)


_ROUND = re.compile(r"\(round (\d+)\)")


def milestones_before(milestones: Sequence[str], round_no: int) -> list[str]:
    """Milestones from rounds before ``round_no``. The season history runs all 38 rounds,
    so later rounds would be the future for this match; milestones without a round are
    dropped too, since their timing is unknown."""
    return [m for m in milestones if (r := _ROUND.search(m)) and int(r.group(1)) < round_no]


def milestone_claims(milestones: Sequence[str]) -> list[Claim]:
    """The numbers in milestone strings ("50th appearance", "round 8") as claims: code wrote
    the milestones, so quoting them is allowed."""
    return [
        Claim(text=m, metric="milestone", value=n.value, unit="", ref="season:milestone")
        for m in milestones
        for n in extract_numbers(m, "en")
        if n.unit not in ("score", "formation")
    ]


async def _ask(agent: Any, message: str, moment_id: str | None, attempt: int) -> tuple[Any, str]:
    """(reply, "") or (None, why the reply was malformed). Service errors are raised."""
    try:
        response = await run_agent(agent, message, moment_id=moment_id, attempt=attempt)
    except ChatClientException as exc:
        problem = bad_reply(exc)
        if problem is None:
            raise
        return None, problem
    return response.value, ""


async def live_line(
    insight: Insight,
    milestones: Sequence[str],
    client: Any,
    *,
    minutes: Collection[int] = (),
) -> str:
    """A live update of at most ``MAX_LINE`` characters, or the insight's headline."""
    agent = make_agent("narrative", PROMPT, LineReply, None, client=client, options=OPTIONS)
    claims = [*insight.claims, *milestone_claims(milestones)]
    payload = {
        "task": "live_line",
        "headline": insight.headline,
        "why": insight.why,
        "claims": [c.model_dump() for c in insight.claims],
        "milestones": list(milestones),
    }
    data = json.dumps(payload, ensure_ascii=False)
    message = f"Write one live line (at most {MAX_LINE} characters).\n{data}"
    problems: list[str] = []
    for attempt in (1, 2):
        text = message if attempt == 1 else (
            f"{message}\n\nYour last line was rejected:\n- " + "\n- ".join(problems)
        )  # fmt: skip
        reply, problem = await _ask(agent, text, insight.moment_id, attempt)
        if not isinstance(reply, LineReply):
            problems = [problem or "the answer was not JSON in the requested shape"]
            continue
        line = " ".join(reply.text.split())
        problems = []
        if not line:
            problems.append("the line is empty")
        if len(line) > MAX_LINE:
            problems.append(
                f"it is {len(line)} characters; it must be at most {MAX_LINE} characters"
            )
        check = check_text(line, "en", claims, lambda c: c.value, minutes=minutes)
        problems += check.failures
        if not problems:
            return line
    head = insight.headline.strip()
    return head if len(head) <= MAX_LINE else head[: MAX_LINE - 1].rstrip() + "…"


def _claims_by_ref(insights: Sequence[Insight]) -> dict[str, Claim]:
    out: dict[str, Claim] = {}
    for i in insights:
        for c in i.claims:
            out.setdefault(c.ref, c)
    return out


def _recap_message(ctx: RecapContext, insights: Sequence[Insight]) -> str:
    h, a = ctx.score
    payload = {
        "score": f"{ctx.home} {h}-{a} {ctx.away}",
        "goals": [{"minute": m, "player": p, "team": t} for m, p, t in ctx.goals],
        "red_cards": [{"minute": m, "player": p, "team": t} for m, p, t in ctx.cards],
        "milestones": ctx.milestones,
        "insights": [{"headline": i.headline, "why": i.why} for i in insights],
        "claims": [c.model_dump() for c in _claims_by_ref(insights).values()],
    }
    data = json.dumps(payload, ensure_ascii=False)
    return f"Write the full-time recap for match {ctx.match_id}.\n{data}"


def template_recap(ctx: RecapContext, insights: Sequence[Insight]) -> Recap:
    """The deterministic recap: result, goals, red cards, and up to 3 key numbers."""
    h, a = ctx.score
    goals = ", ".join(f"{p} ({t}) {m}" for m, p, t in ctx.goals) or "none"
    paragraphs = [f"Goals: {goals}."]
    if ctx.cards:
        paragraphs.append(
            "Red cards: " + ", ".join(f"{p} ({t}) {m}" for m, p, t in ctx.cards) + "."
        )
    key = list(_claims_by_ref(insights).values())[:MAX_KEY_NUMBERS]
    lines = [
        f"{LABELS[c.metric]['en']}: {format_value(c, 'en')}" for c in key if c.metric in LABELS
    ]
    if lines:
        paragraphs.append("Key numbers: " + "; ".join(lines) + ".")
    return Recap(
        match_id=ctx.match_id, title=f"Full time: {ctx.home} {h}-{a} {ctx.away}",
        paragraphs=paragraphs, key_numbers=[c for c in key if c.metric in LABELS],
        verified=True, source="template",
    )  # fmt: skip


async def recap(ctx: RecapContext, insights: Sequence[Insight], client: Any) -> Recap:
    """The full-time recap. Its numbers must be cited claims (``key_refs``), real minutes,
    or real scorelines; one regeneration, then ``template_recap``."""
    agent = make_agent("narrative", PROMPT, RecapReply, None, client=client, options=OPTIONS)
    by_ref = _claims_by_ref(insights)
    message = _recap_message(ctx, insights)
    problems: list[str] = []
    for attempt in (1, 2):
        text = message if attempt == 1 else (
            f"{message}\n\nYour last recap was rejected:\n- " + "\n- ".join(problems)
        )  # fmt: skip
        reply, problem = await _ask(agent, text, None, attempt)
        if not isinstance(reply, RecapReply):
            problems = [problem or "the answer was not JSON in the requested shape"]
            continue
        unknown = [r for r in reply.key_refs if r not in by_ref]
        cited = [by_ref[r] for r in reply.key_refs if r in by_ref]
        problems = [f"key_refs {r!r} is not one of the claims' refs" for r in unknown]
        body = "\n".join([reply.title, *reply.paragraphs])
        check = check_text(
            body, "en", [*cited, *milestone_claims(ctx.milestones)], lambda c: c.value,
            minutes=ctx.minutes, scores=ctx.scores,
        )  # fmt: skip
        problems += [
            f + " (cite the claim's ref in key_refs, or remove the number)"
            if "matches no verified" in f else f
            for f in check.failures
        ]  # fmt: skip
        if not reply.paragraphs:
            problems.append("paragraphs is empty")
        if not problems:
            return Recap(
                match_id=ctx.match_id, title=reply.title, paragraphs=reply.paragraphs,
                key_numbers=cited, verified=True, source="agent",
            )  # fmt: skip
    return template_recap(ctx, insights)


def recap_context(repo: Any, match_id: str) -> RecapContext:
    """The result, goals, red cards, and both clubs' and scorers' milestones, from the store."""
    from matchmind.agents.context import match_names  # noqa: PLC0415
    from matchmind.agents.verifier import _scorelines  # noqa: PLC0415

    meta = repo.get_match_meta(match_id)
    if meta is None:
        raise KeyError(f"unknown match {match_id!r}")
    names = match_names(meta)
    events = repo.get_events(match_id)
    goals = [e for e in events if e.type == "goal"]
    reds = [e for e in events if e.type == "card" and e.extras.get("card") != "yellow"]
    home_id = meta.home.club_id
    score = (sum(g.team_id == home_id for g in goals), sum(g.team_id != home_id for g in goals))
    season = repo.load_season()
    people = [meta.home.club_id, meta.away.club_id, *(g.player_id for g in goals if g.player_id)]
    found = re.match(r"^r(\d+)-", match_id)
    round_no = int(found.group(1)) if found else 0
    milestones = milestones_before(
        [
            f"{names.get(who, who)}: {m}"
            for who in dict.fromkeys(people)
            for m in (season.milestones.get(who, []) if season else [])
        ],
        round_no,
    )

    def row(e: Any) -> tuple[str, str, str]:
        return minute_label(e.period, e.t), names.get(e.player_id or "", ""), names[e.team_id]

    return RecapContext(
        match_id=match_id, home=meta.home.name, away=meta.away.name, score=score,
        goals=[row(g) for g in goals], cards=[row(e) for e in reds], milestones=milestones,
        minutes={match_minute(e.period, e.t) for e in events},
        scores=_scorelines(events, home_id),
    )  # fmt: skip
