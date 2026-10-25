"""Verifier: nothing reaches the screen until it passes (Constitution II).

Two stages, in order:
1. **Numbers (deterministic, authoritative).** Every claim is looked up by its ref, at the
   same event-exact time the tools used, and every number in the text must match a
   verified claim, a real event minute, a real scoreline, or a formation actually used
   (``numbers.check_text``, in the text's own language). A failure here can't be
   overridden: the model isn't even asked.
2. **Wording (the model).** The Verifier agent reads the text against the cited events
   (who, where, when, which side) and lists anything they don't support.

``verify_loop`` runs Explainer → Verifier, feeding failures back, for at most two
regenerations; after that it returns None and the pipeline shows a template (TASK-20).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal, Protocol

from agent_framework.exceptions import ChatClientException
from opentelemetry.trace import Tracer
from pydantic import BaseModel

from matchmind.agents.context import match_names
from matchmind.agents.explainer import ExplainerError, explain
from matchmind.agents.numbers import check_text, fold
from matchmind.agents.runtime import bad_reply, make_agent, run_agent
from matchmind.clock import match_minute, minute_label
from matchmind.engine.pitch import PITCH_LENGTH, attacks_right
from matchmind.schemas import AnalystDecision, Claim, Event, Insight, Lang, Moment, Verdict

log = logging.getLogger(__name__)
PROMPT = "verifier.v1.md"
MAX_REGENERATIONS = 2
_REF = re.compile(
    r"^(?P<kind>metric|deviation):(?P<name>[^@]+)@(?P<period>[12]):(?P<t>[\d.]+)"
    r"/(?P<scope>team|player):(?P<scope_id>.+)$"
)
_DEVIATION_FIELDS = ("expected", "baseline_per90", "p_value")


class Facts(Protocol):
    """What the Verifier checks against, for one match."""

    names: Mapping[str, str]
    minutes: set[int]
    scores: set[tuple[int, int]]
    formations: set[str]

    def lookup(self, claim: Claim) -> float | None: ...

    def events(self, event_ids: list[str]) -> list[Event]: ...

    def third(self, event: Event) -> str:
        """``attacking``, ``middle``, or ``defensive``, for the team that made the event."""
        ...

    def before(self, event: Event) -> list[Event]:
        """The few events just before ``event``, oldest first (to check stated causes)."""
        ...


Verdict_ = Literal["supported", "not_covered", "contradicted", "invented"]
FAILING: frozenset[str] = frozenset({"contradicted", "invented"})


class StatementCheck(BaseModel):
    """One statement of the text and what the cited events say about it."""

    statement: str
    verdict: Verdict_
    reason: str


class VerifierReply(BaseModel):
    """The Verifier agent checks the text statement by statement: listing each one makes it
    look at every clause (a single ok/problems answer skimmed past invented causes)."""

    checks: list[StatementCheck]


def insight_text(insight: Insight) -> str:
    """The text a fan reads: headline, explanation, recommendation."""
    return "\n".join([insight.headline, insight.why, insight.recommendation])


def _numbers(
    insight: Insight, lang: Lang, text: str, facts: Facts
) -> tuple[list[str], list[Claim]]:
    stored = {c.ref + c.metric: facts.lookup(c) for c in insight.claims}
    check = check_text(
        text,
        lang,
        insight.claims,
        lambda c: stored[c.ref + c.metric],
        minutes=facts.minutes,
        scores=facts.scores,
        formations=facts.formations,
    )
    fixed = [
        c.model_copy(update={"value": value})
        for c in insight.claims
        if (value := stored[c.ref + c.metric]) is not None
        and any(c.text in f and "but the stats say" in f for f in check.failures)
    ]
    failures = [
        f
        + (
            ": every number needs its own claim (its own metric, value, and ref from a stats "
            "tool), or remove it"
            if "matches no verified" in f
            else ""
        )
        for f in check.failures
    ]
    return failures, fixed


CONTEXT_EVENTS = 3
# "first half" / "second half" in each language, accent- and hamza-folded (numbers.fold).
_HALVES: dict[str, dict[int, tuple[str, ...]]] = {
    "en": {1: ("first half", "first-half"), 2: ("second half", "second-half")},
    "es": {1: ("primer tiempo", "primera parte", "primera mitad"),
           2: ("segundo tiempo", "segunda parte", "segunda mitad")},
    "pt": {1: ("primeiro tempo", "primeira parte"), 2: ("segundo tempo", "segunda parte")},
    "fr": {1: ("premiere mi-temps", "premiere periode"),
           2: ("deuxieme mi-temps", "seconde mi-temps", "deuxieme periode", "seconde periode")},
    "ar": {1: ("الشوط الاول",), 2: ("الشوط الثاني",)},
}  # fmt: skip


def _halves(insight: Insight, lang: Lang, text: str, facts: Facts) -> list[str]:
    """The half the text names must be the half its cited events are in."""
    periods = {e.period for e in facts.events(insight.event_ids)}
    folded = fold(text)
    name = {1: "first", 2: "second"}
    return [
        f"the text says the {name[half]} half, but its events are in the "
        f"{' and '.join(name[p] for p in sorted(periods))} half"
        for half, phrases in _HALVES[lang].items()
        if periods and half not in periods and any(p in folded for p in phrases)
    ]


def _fact_view(c: Claim, facts: Facts) -> dict[str, str]:
    """A verified claim as the Verifier agent reads it: the statement and whose it is, by
    name. No value: numbers are the deterministic check's job, and showing them invited the
    model to re-check rounding ("43%" against 42.5%) in the first evaluation."""
    if m := _REF.match(c.ref):
        about = facts.names.get(m["scope_id"], m["scope_id"])
    else:
        events = facts.events([c.ref])
        about = facts.names.get(events[0].player_id or events[0].team_id, "") if events else ""
    return {"statement": c.text, "about": about}


def _event_view(e: Event, facts: Facts, context: bool = True) -> dict[str, Any]:
    names = facts.names
    view: dict[str, Any] = {
        "event_id": e.event_id,
        "minute": minute_label(e.period, e.t),
        "type": e.type,
        "team": names.get(e.team_id, e.team_id),
        "player": names.get(e.player_id or "", e.player_id),
        "third": facts.third(e),
        "y": e.y,
        "outcome": e.outcome,
        "receiver": names.get(e.receiver_id or "", e.receiver_id),
    }
    if context:
        view["just_before"] = [_event_view(b, facts, False) for b in facts.before(e)]
    return view


async def _wording(
    insight: Insight, lang: Lang, text: str, facts: Facts, client: Any, tracer: Tracer | None
) -> list[str]:
    agent = make_agent(
        "verifier", PROMPT, VerifierReply, None, client=client, options={"temperature": 0.0}
    )
    payload = {
        "lang": lang,
        "level": insight.level,
        "text": text,
        "facts": [_fact_view(c, facts) for c in insight.claims],
        "events": [_event_view(e, facts) for e in facts.events(insight.event_ids)],
    }
    message = f"Check this insight for moment {insight.moment_id}.\n{json.dumps(payload)}"
    problem = ""
    for attempt in (1, 2):
        text_in = message if attempt == 1 else f"{message}\n\nAnswer in the requested JSON shape."
        try:
            response = await run_agent(
                agent, text_in, moment_id=insight.moment_id, attempt=attempt, tracer=tracer
            )
        except ChatClientException as exc:
            problem = bad_reply(exc) or ""
            if not problem:
                raise
            continue
        reply = response.value
        if isinstance(reply, VerifierReply) and reply.checks:
            return [
                f"qualitative: {c.statement!r}: {c.reason}"
                for c in reply.checks
                if c.verdict in FAILING
            ]
        problem = "the reply was not JSON in the requested shape"
    return [f"qualitative: the Verifier could not judge the text ({problem})"]  # fail closed


async def verify(
    insight: Insight,
    lang: Lang,
    text: str,
    facts: Facts,
    client: Any,
    *,
    tracer: Tracer | None = None,
) -> Verdict:
    """Verify ``text`` (``insight`` or its translation into ``lang``) against ``facts``."""
    failures, fixed = _numbers(insight, lang, text, facts)
    failures += _halves(insight, lang, text, facts)
    if not failures:
        failures = await _wording(insight, lang, text, facts, client, tracer)
    return Verdict(ok=not failures, failures=failures, fixed_claims=fixed)


async def verify_loop(
    decision: AnalystDecision,
    moment: Moment,
    client: Any,
    tools: Any,
    facts: Facts,
    *,
    max_regenerations: int = MAX_REGENERATIONS,
    on_attempt: Callable[[Insight, Verdict], None] | None = None,
    tracer: Tracer | None = None,
) -> Insight | None:
    """Explainer → Verifier, regenerating with the failures, at most ``max_regenerations``
    times. Returns the verified insight, or None (show a template). ``on_attempt`` sees
    every draft and its verdict (the fixture recorder and agent-run logging use it)."""
    feedback = None
    for _ in range(1 + max_regenerations):
        try:
            insight = await explain(
                decision, moment, client, tools,
                names=facts.names, feedback=feedback, tracer=tracer,
            )  # fmt: skip
        except ExplainerError as exc:
            log.warning("Explainer gave up: %s", exc)
            return None
        verdict = await verify(insight, "en", insight_text(insight), facts, client, tracer=tracer)
        if on_attempt is not None:
            on_attempt(insight, verdict)
        if verdict.ok:
            return insight.model_copy(update={"verified": True})
        feedback = "\n".join(f"- {f}" for f in verdict.failures)
    return None


class DictFacts:
    """Facts written down as data: what the Verifier looked up, saved with a recording or a
    golden-set line (``names``, ``minutes``, ``scores``, ``formations``, ``lookups`` keyed
    ``ref|metric|unit``, ``events``, ``thirds``), so they replay without the database."""

    def __init__(self, facts: Mapping[str, Any]) -> None:
        self.names: Mapping[str, str] = facts["names"]
        self.minutes = set(facts["minutes"])
        self.scores = {(int(a), int(b)) for a, b in facts["scores"]}
        self.formations = set(facts["formations"])
        self._lookups: Mapping[str, float | None] = facts["lookups"]
        self._events = {k: Event(**v) for k, v in facts["events"].items()}
        self._thirds: Mapping[str, str] = facts["thirds"]
        self._before: Mapping[str, list[dict[str, Any]]] = facts.get("before", {})

    def lookup(self, claim: Claim) -> float | None:
        return self._lookups.get(f"{claim.ref}|{claim.metric}|{claim.unit}")

    def events(self, event_ids: list[str]) -> list[Event]:
        return [self._events[e] for e in event_ids if e in self._events]

    def third(self, event: Event) -> str:
        return self._thirds[event.event_id]

    def before(self, event: Event) -> list[Event]:
        return [Event(**e) for e in self._before.get(event.event_id, [])]


class StatsFacts:
    """Facts for one match from the stats service: the same event-exact values the MCP
    tools returned, so a claim read from a tool always verifies against itself."""

    def __init__(self, stats: Any, match_id: str) -> None:
        from matchmind.stats.deviations import detect_deviations  # noqa: PLC0415

        self._detect = detect_deviations
        self.stats, self.match_id = stats, match_id
        repo = stats.repo
        meta = repo.get_match_meta(match_id)
        if meta is None:
            raise KeyError(f"unknown match {match_id!r}")
        self.meta = meta
        self.names: Mapping[str, str] = match_names(meta)
        events = repo.get_events(match_id)
        self._events = {e.event_id: e for e in events}
        self._order = sorted(events, key=lambda e: (e.period, e.t))
        self._index = {e.event_id: i for i, e in enumerate(self._order)}
        self.minutes = {match_minute(e.period, e.t) for e in events}
        self.scores = _scorelines(events, meta.home.club_id)
        self.formations = {meta.home.formation, meta.away.formation} | {
            shape
            for m in repo.list_moments(match_id)
            if m.trigger_metric.startswith("formation:")
            for shape in m.trigger_metric.removeprefix("formation:").split("->")
        }

    def events(self, event_ids: list[str]) -> list[Event]:
        return [self._events[e] for e in event_ids if e in self._events]

    def before(self, event: Event) -> list[Event]:
        i = self._index.get(event.event_id, 0)
        return self._order[max(0, i - CONTEXT_EVENTS) : i]

    def third(self, event: Event) -> str:
        right = attacks_right(event.team_id == self.meta.home.club_id, event.period)
        forward = event.x if right else PITCH_LENGTH - event.x
        return "attacking" if forward > 70.0 else "defensive" if forward < 35.0 else "middle"

    def lookup(self, claim: Claim) -> float | None:
        if m := _REF.match(claim.ref):
            period, t = int(m["period"]), float(m["t"])
            if m["kind"] == "metric":
                if claim.metric != m["name"]:
                    return None
                snap = self.stats.snapshot(self.meta, period, t)
                value = snap.get((m["scope"], m["scope_id"]), {}).get(m["name"])
                return None if value is None else float(value)
            return self._deviation(claim, m["name"], m["scope_id"], period, t)
        event = self._events.get(claim.ref)
        if event is None:
            return None
        if claim.metric.startswith("counterfactual"):
            cf = self.stats.get_counterfactual(event.event_id)
            return float(cf["gain"]) if "gain" in cf else None
        return _event_value(event, claim)

    def _deviation(
        self, claim: Claim, stat: str, player_id: str, period: int, t: float
    ) -> float | None:
        baselines = self.stats.baselines()
        if baselines is None:
            return None
        data = self.stats.match_upto(self.meta, period, t, frame=False)
        for d in self._detect(data, baselines, (period, t)):
            if d.player_id == player_id and d.stat == stat:
                field = claim.metric.removeprefix(f"{stat}_")
                if claim.metric == stat:
                    return float(d.observed)
                if field in _DEVIATION_FIELDS:
                    return float(getattr(d, field))
        return None


def _event_value(event: Event, claim: Claim) -> float | None:
    """A number read off one event: a field, an extra, or 1 for the event itself."""
    if claim.metric in ("ball_speed", "ball_speed_ms", "shot_speed") and event.ball_speed_ms:
        speed = event.ball_speed_ms
        return speed * 3.6 if claim.unit.strip().lower() == "km/h" else speed
    value = getattr(event, claim.metric, None)
    if value is None:
        value = event.extras.get(claim.metric)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if claim.metric in (event.type, f"{event.type}s"):
        return 1.0
    return None


def _scorelines(events: Sequence[Event], home_id: str) -> set[tuple[int, int]]:
    """Every score the match passed through, home first, from 0-0 to the final score."""
    home = away = 0
    seen = {(0, 0)}
    for e in sorted(events, key=lambda e: (e.period, e.t)):
        if e.type == "goal":
            home, away = (home + 1, away) if e.team_id == home_id else (home, away + 1)
            seen.add((home, away))
    return seen
