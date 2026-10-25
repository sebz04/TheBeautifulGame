"""The insight pipeline as an Agent Framework workflow, one graph run per 5-minute window.

    analyst ─▶ explainer_verifier ─▶ narrative ─▶ personalizer_verifier
    (which      (Explainer ⟲ Verifier,   (live line)   (one call per language for every fan,
     moments)    ≤ 2 regenerations)                     then the Verifier in that language)

Every step degrades instead of failing: a moment whose explanation can't be verified gets a
template insight, a missing live line becomes the headline, and a fan text that fails gets
its template, so each surfaced moment still has a card in every language (Constitution II).
Timeouts and 429s are retried with backoff inside ``run_agent``; every agent call and every
fallback is written to ``agent_runs``. Work already stored is skipped, so precompute can be
re-run safely after an interruption.
"""

import asyncio
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Never

from agent_framework import Workflow, WorkflowBuilder, WorkflowContext, executor

from matchmind.agents.analyst import analyze, batches
from matchmind.agents.context import match_names
from matchmind.agents.narrative import live_line, recap, recap_context
from matchmind.agents.numbers import fold
from matchmind.agents.personalizer import personalize_batch as _personalize
from matchmind.agents.personalizer import variants_for
from matchmind.agents.runtime import RunLog, TokenBucket, pipeline_scope
from matchmind.agents.templates import render
from matchmind.agents.verifier import Facts, verify, verify_loop
from matchmind.clock import minute_label
from matchmind.schemas import (
    AgentRun,
    AnalystDecision,
    Insight,
    Lang,
    MatchMeta,
    Moment,
    PersonalizedText,
)
from matchmind.store.db import Repo

ALL_LANGS: tuple[Lang, ...] = ("en", "es", "pt", "fr", "ar")
TEMPLATE_PROMPT = "template.v1"
_QUOTED = re.compile(r"'(.+?)':|“…(.+?)…”")

TEMPLATE_HEADLINES = {
    "goal": "Goal for {team}",
    "red_card": "Red card for {team}",
    "big_chance": "Big chance for {team}",
    "momentum_swing": "Momentum swings to {team}",
    "pressing_collapse": "{team}'s press drops off",
    "formation_shift": "{team} change shape",
    "offside_trap": "{team} spring the offside trap",
    "corner_pressure": "{team} pile on corner pressure",
    "player_deviation": "{player} stands out",
    "sprint_alert": "{player} on the move",
}


@dataclass
class Deps:
    """What the pipeline needs: the store, the model, the stats tools, and the facts the
    Verifier checks against (per match). ``sleep`` is the backoff clock (tests pass a fake)."""

    repo: Repo
    client: Any
    tools: Any
    facts_for: Callable[[str], Facts]
    sleep: Callable[[float], Any] = asyncio.sleep
    langs: Sequence[Lang] = ALL_LANGS
    limiter: TokenBucket | None = None
    max_parallel: int = 4


@dataclass
class WindowReport:
    match_id: str
    period: int
    t_from: float
    t_to: float
    moments: int = 0
    surfaced: int = 0
    skipped: int = 0
    insights: int = 0
    verified: int = 0
    templated: int = 0
    personalized: int = 0
    personalized_templated: int = 0
    runs: list[AgentRun] = field(default_factory=list)


@dataclass
class PipelineReport:
    match_id: str
    insights: int
    verified: int
    templated: int
    skipped: int
    personalized: int
    personalized_templated: int
    agent_runs: int
    p95_latency_ms: float
    tokens_in: int
    tokens_out: int
    recap_source: str | None


@dataclass
class WindowJob:
    match_id: str
    period: int
    t_from: float
    t_to: float


@dataclass
class _Window:
    """State shared by the steps of one window run.

    The workflow deep-copies messages between steps; this state (the store, the facts with
    their database engine, the run log) is shared on purpose and can't be copied, so a copy
    is the same object. No checkpoints are used, so nothing needs to serialize it.
    """

    def __deepcopy__(self, memo: dict[int, Any]) -> "_Window":
        return self

    job: WindowJob
    meta: MatchMeta
    facts: Facts
    names: Mapping[str, str]
    report: WindowReport
    log: RunLog
    existing: dict[str, Insight]


@dataclass
class Surfaced:
    win: _Window
    todo: list[tuple[AnalystDecision, Moment]]
    carried: list[Insight]  # already explained, but lines or texts are missing


@dataclass
class Explained:
    win: _Window
    insights: list[Insight]


def _fallback(log: RunLog, step: str, moment_id: str, reason: str) -> None:
    log.runs.append(AgentRun(
        run_id=uuid.uuid4().hex, agent=f"template:{step}", moment_id=moment_id,
        status="fallback", attempts=0, latency_ms=0, trace_id=None, error=reason[:500],
    ))  # fmt: skip


def template_insight(moment: Moment, level: str, names: Mapping[str, str]) -> Insight:
    """The card shown when no explanation could be verified: what happened, when, no numbers."""
    who = {"team": names.get(moment.team_id or "", "The match"),
           "player": names.get(moment.player_id or "", "A player")}  # fmt: skip
    headline = TEMPLATE_HEADLINES.get(moment.kind, "A key moment").format(**who)
    rec = "Watch how the next few minutes unfold."
    return Insight(
        insight_id=f"{moment.moment_id}-ins", moment_id=moment.moment_id,
        match_id=moment.match_id, level=level,
        headline=headline, why=f"{headline} at {minute_label(moment.period, moment.t_end)}.",
        recommendation=rec, claims=[], event_ids=moment.event_ids or [], confidence="low",
        verified=True, source="template", trace_id=None, prompt_version=TEMPLATE_PROMPT,
    )  # fmt: skip


async def _gather(limit: int, coros: Sequence[Any]) -> list[Any]:
    sem = asyncio.Semaphore(limit)

    async def one(c: Any) -> Any:
        async with sem:
            return await c

    return list(await asyncio.gather(*(one(c) for c in coros)))


# ---- steps ----------------------------------------------------------------------------------


def _open_window(job: WindowJob, deps: Deps, log: RunLog) -> tuple[_Window, list[Moment]]:
    repo = deps.repo
    meta = repo.get_match_meta(job.match_id)
    if meta is None:
        raise KeyError(f"unknown match {job.match_id!r}")
    moments = [
        m for m in repo.list_moments(job.match_id)
        if m.period == job.period and job.t_from <= m.t_start < job.t_to
    ]  # fmt: skip
    existing = {i.moment_id: i for i in repo.list_insights(job.match_id)}
    report = WindowReport(job.match_id, job.period, job.t_from, job.t_to, moments=len(moments))
    win = _Window(job, meta, deps.facts_for(job.match_id), match_names(meta), report, log,
                  existing)  # fmt: skip
    return win, moments


def _complete(win: _Window, deps: Deps, insight: Insight) -> bool:
    lines = deps.repo.list_live_lines(win.job.match_id)
    if insight.insight_id not in lines:
        return False
    return all(
        any(t.insight_id == insight.insight_id
            for t in deps.repo.list_personalized(win.job.match_id, lang=lang))
        for lang in deps.langs
    )  # fmt: skip


async def analyst_step(job: WindowJob, deps: Deps, log: RunLog) -> Surfaced:
    win, moments = _open_window(job, deps, log)
    carried = [win.existing[m.moment_id] for m in moments if m.moment_id in win.existing]
    win.report.skipped = sum(_complete(win, deps, i) for i in carried)
    carried = [i for i in carried if not _complete(win, deps, i)]
    fresh = [m for m in moments if m.moment_id not in win.existing]
    decisions: list[AnalystDecision] = []
    if fresh:
        try:
            decisions = await analyze(fresh, deps.client, deps.tools, names=win.names)
        except Exception as exc:  # the model is down: nothing surfaces this window
            _fallback(log, "analyst", fresh[0].moment_id, f"analyst failed: {exc}")
    by_id = {m.moment_id: m for m in fresh}
    todo = [(d, by_id[d.moment_id]) for d in decisions]
    win.report.surfaced = len(todo)
    return Surfaced(win, todo, carried)


async def explain_step(s: Surfaced, deps: Deps) -> Explained:
    win = s.win

    async def one(decision: AnalystDecision, moment: Moment) -> Insight:
        try:
            insight = await verify_loop(decision, moment, deps.client, deps.tools, win.facts)
        except Exception as exc:
            insight, reason = None, f"explainer failed: {exc}"
        else:
            reason = "no verified explanation after 2 regenerations"
        if insight is None:
            _fallback(win.log, "explainer", moment.moment_id, reason)
            insight = template_insight(moment, decision.level, win.names)
        deps.repo.save_insight(insight)
        return insight

    made = await _gather(deps.max_parallel, [one(d, m) for d, m in s.todo])
    insights = [*s.carried, *made]
    win.report.insights = len(insights)
    win.report.verified = sum(i.source == "agent" for i in insights)
    win.report.templated = sum(i.source == "template" for i in insights)
    return Explained(win, insights)


async def narrative_step(e: Explained, deps: Deps) -> Explained:
    win = e.win
    have = deps.repo.list_live_lines(win.job.match_id)

    async def one(insight: Insight) -> None:
        if insight.insight_id in have:
            return
        if insight.source == "template":
            line = insight.headline
        else:
            try:
                line = await live_line(insight, [], deps.client, minutes=win.facts.minutes)
            except Exception as exc:
                _fallback(win.log, "narrative", insight.moment_id, f"live line failed: {exc}")
                line = insight.headline
        deps.repo.save_live_line(win.job.match_id, insight.insight_id, line)

    await _gather(deps.max_parallel, [one(i) for i in e.insights])
    return e


def _bad_variants(failures: list[str], texts: list[PersonalizedText]) -> list[PersonalizedText]:
    """The texts the Verifier's failures point at (by quoted statement); all if unclear."""
    quoted = [fold(a or b) for f in failures for a, b in _QUOTED.findall(f)]
    hit = [t for t in texts if any(q and q in fold(f"{t.headline}\n{t.body}") for q in quoted)]
    return hit or texts


async def verify_texts(
    insight: Insight, lang: Lang, texts: list[PersonalizedText], win: _Window, deps: Deps
) -> list[PersonalizedText]:
    """One Verifier call for all the agent-written texts of an insight in one language."""
    agent = [t for t in texts if not t.verified]
    if not agent:
        return texts
    combined = "\n\n".join(f"{t.headline}\n{t.body}" for t in agent)
    try:
        verdict = await verify(insight, lang, combined, win.facts, deps.client)
        failures = verdict.failures
    except Exception as exc:
        failures = [f"verifier failed: {exc}"]
    bad = _bad_variants(failures, agent) if failures else []
    out = []
    for t in texts:
        if t in bad:
            _fallback(win.log, "personalizer", insight.moment_id,
                      f"{lang} {t.persona}: " + "; ".join(failures))  # fmt: skip
            key = (t.persona, t.club_id, t.player_id)
            v = next(
                v for v in variants_for(insight, win.meta)
                if (v.persona, v.club_id, v.player_id) == key
            )  # fmt: skip
            out.append(render(insight, v, lang, win.names))
        else:
            out.append(t if t.verified else t.model_copy(update={"verified": True}))
    return out


async def personalize_step(e: Explained, deps: Deps) -> WindowReport:
    win = e.win
    scores: set[tuple[int, int]] = set(win.facts.scores)

    async def one(insight: Insight, lang: Lang) -> list[PersonalizedText]:
        stored = deps.repo.list_personalized(win.job.match_id, lang=lang)
        if any(t.insight_id == insight.insight_id for t in stored):
            return []
        variants = variants_for(insight, win.meta)
        if insight.source == "template":
            texts = [render(insight, v, lang, win.names) for v in variants]
        else:
            try:
                texts = await _personalize(insight, lang, variants, deps.client, names=win.names,
                                           minutes=win.facts.minutes, scores=scores)  # fmt: skip
            except Exception as exc:
                _fallback(win.log, "personalizer", insight.moment_id, f"{lang} failed: {exc}")
                texts = [render(insight, v, lang, win.names) for v in variants]
            texts = await verify_texts(insight, lang, texts, win, deps)
        deps.repo.save_personalized(texts)
        return texts

    made = await _gather(
        deps.max_parallel, [one(i, lang) for i in e.insights for lang in deps.langs]
    )
    texts = [t for group in made for t in group]
    win.report.personalized = len(texts)
    win.report.personalized_templated = sum(t.source == "template" for t in texts)
    return win.report


# ---- the workflow ---------------------------------------------------------------------------


def build_workflow(deps: Deps, log: RunLog | None = None) -> Workflow:
    """The window pipeline as an Agent Framework graph (also what DevUI shows)."""
    log = log if log is not None else RunLog()

    @executor(id="analyst")
    async def analyst_exec(job: WindowJob, ctx: WorkflowContext[Surfaced]) -> None:
        await ctx.send_message(await analyst_step(job, deps, log))

    @executor(id="explainer_verifier")
    async def explainer_exec(s: Surfaced, ctx: WorkflowContext[Explained]) -> None:
        await ctx.send_message(await explain_step(s, deps))

    @executor(id="narrative")
    async def narrative_exec(e: Explained, ctx: WorkflowContext[Explained]) -> None:
        await ctx.send_message(await narrative_step(e, deps))

    @executor(id="personalizer_verifier")
    async def personalizer_exec(e: Explained, ctx: WorkflowContext[Never, WindowReport]) -> None:
        await ctx.yield_output(await personalize_step(e, deps))

    steps = [analyst_exec, explainer_exec, narrative_exec, personalizer_exec]
    return (
        WorkflowBuilder(
            name="matchmind-insights",
            description="Analyst → Explainer ⟲ Verifier → Narrative → Personalizer → Verifier",
            start_executor=analyst_exec,
        )
        .add_chain(steps)
        .build()
    )


async def run_window(
    match_id: str, period: int, t_from: float, t_to: float, deps: Deps
) -> WindowReport:
    """Run the pipeline for the moments starting in [t_from, t_to) of ``period``."""
    log = RunLog()
    with pipeline_scope(log=log, sleep=deps.sleep, limiter=deps.limiter):
        result = await build_workflow(deps, log).run(WindowJob(match_id, period, t_from, t_to))
    (report,) = result.get_outputs()
    assert isinstance(report, WindowReport)
    for run in log.runs:
        deps.repo.log_agent_run(run)
    report.runs = list(log.runs)
    return report


def _p95(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))])


async def run_match(
    match_id: str, deps: Deps, *, max_windows: int = 2, limit: int | None = None
) -> PipelineReport:
    """Every window of the match, then the full-time recap; returns the totals. ``limit``
    runs only the first windows (a smoke test) and skips the recap."""
    moments = deps.repo.list_moments(match_id)
    windows = [
        (b[0].period, b[0].t_start, b[-1].t_start + 1e-6) for b in batches(moments)
    ]  # fmt: skip
    windows = windows[:limit] if limit is not None else windows
    reports = await _gather(
        max_windows, [run_window(match_id, p, a, z, deps) for p, a, z in windows]
    )
    runs = [r for rep in reports for r in rep.runs]
    recap_source = None
    existing = deps.repo.get_recap(match_id)
    if limit is not None:
        pass  # a partial run: no recap
    elif existing is None:
        log = RunLog()
        insights = [i for i in deps.repo.list_insights(match_id) if i.source == "agent"]
        with pipeline_scope(log=log, sleep=deps.sleep, limiter=deps.limiter):
            try:
                result = await recap(recap_context(deps.repo, match_id), insights, deps.client)
            except Exception as exc:
                from matchmind.agents.narrative import template_recap  # noqa: PLC0415

                _fallback(log, "recap", f"{match_id}-recap", f"recap failed: {exc}")
                result = template_recap(recap_context(deps.repo, match_id), insights)
        deps.repo.save_recap(result)
        for run in log.runs:
            deps.repo.log_agent_run(run)
        runs += log.runs
        recap_source = result.source
    else:
        recap_source = existing.source
    stored = deps.repo.list_insights(match_id)
    agent_runs = [r for r in runs if r.status != "fallback"]
    return PipelineReport(
        match_id=match_id,
        insights=len(stored),
        verified=sum(i.source == "agent" for i in stored),
        templated=sum(i.source == "template" for i in stored),
        skipped=sum(r.skipped for r in reports),
        personalized=sum(r.personalized for r in reports),
        personalized_templated=sum(r.personalized_templated for r in reports),
        agent_runs=len(agent_runs),
        p95_latency_ms=_p95([r.latency_ms for r in agent_runs]),
        tokens_in=sum(r.tokens_in for r in runs),
        tokens_out=sum(r.tokens_out for r in runs),
        recap_source=recap_source,
    )
