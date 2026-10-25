"""The orchestrator end to end, with one fake model playing all five agents."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from agent_framework.exceptions import ChatClientException
from conftest import StatsStub

from matchmind.agents.orchestrator import Deps, build_workflow, run_match, run_window
from matchmind.agents.runtime import FakeCall, FakeChatClient, FakeReply, tool_call
from matchmind.agents.verifier import DictFacts
from matchmind.engine.lineup import match_meta
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.schemas import MatchData, Moment
from matchmind.store.db import Repo

LANGS = ("en", "es")


@dataclass
class World:
    repo: Repo
    match_id: str
    home: str
    away: str
    names: dict[str, str]
    ppda_ref: str
    sleeps: list[float] = field(default_factory=list)


def _world() -> World:
    league = build_league()
    meta = match_meta(league, build_fixtures(league, seed=2026)[0], seed=7)
    repo = Repo("sqlite://")
    repo.save_match_data(MatchData(meta=meta, events=[], frames=[]))
    mid, home, away = meta.match_id, meta.home.club_id, meta.away.club_id
    moments = [
        Moment(moment_id=f"{mid}-m00{i}", match_id=mid, period=1, t_start=60.0 * i,
               t_end=60.0 * i + 30, kind=kind, level="team", team_id=home, player_id=None,
               trigger_metric="x", trigger_value=1.0, event_ids=[f"{mid}-e0000{i}"])
        for i, kind in ((1, "pressing_collapse"), (2, "big_chance"))
    ]  # fmt: skip
    repo.save_moments(mid, moments)
    names = {meta.home.club_id: meta.home.name, meta.away.club_id: meta.away.name}
    names |= {p.player_id: p.name for p in [*meta.home_squad, *meta.away_squad]}
    ppda_ref = f"metric:ppda_10min@1:150.0/team:{home}"
    return World(repo, mid, home, away, names, ppda_ref)


def _facts(w: World) -> DictFacts:
    return DictFacts({
        "names": w.names, "minutes": list(range(1, 91)), "scores": [[0, 0]], "formations": [],
        "lookups": {f"{w.ppda_ref}|ppda_10min|": 6.4}, "events": {}, "thirds": {},
    })  # fmt: skip


def _agent(call: FakeCall) -> str:
    return call.instructions.split("\n", 1)[0]


def _model(
    w: World,
    *,
    explainer: Callable[[int], str] | None = None,
    fail: Callable[[str, int], Exception | None] | None = None,
) -> FakeChatClient:
    """A fake model for all five agents. ``explainer(n)`` gives the n-th explanation's
    "why"; ``fail(agent, n)`` may raise for the n-th call of an agent."""
    counts: dict[str, int] = {}

    def reply(call: FakeCall) -> FakeReply:
        agent = _agent(call)
        counts[agent] = counts.get(agent, 0) + 1
        if fail and (exc := fail(agent, counts[agent])):
            raise exc
        if "Tactical Analyst" in agent:
            ids = re.findall(r'"moment_id": "([^"]+)"', call.text)
            if not call.tool_results:
                return [tool_call("get_moment", moment_id=i) for i in ids]
            return json.dumps({"decisions": [
                {"moment_id": i, "surface": True, "level": "team", "priority": 3,
                 "tactical_context": "The press dropped.", "metrics_to_cite": ["ppda_10min"]}
                for i in ids
            ]})  # fmt: skip
        if "Explainer" in agent:
            n = sum(v for k, v in counts.items() if "Explainer" in k)
            why = explainer(n) if explainer else "They allow 6.4 passes per defensive action."
            ev = re.search(r'"event_ids": \["([^"]+)"', call.text)
            return json.dumps({
                "headline": "The press switched on", "why": why, "recommendation": "Keep it up.",
                "claims": [{"text": "6.4 passes", "metric": "ppda_10min", "value": 6.4, "unit": "",
                            "ref": w.ppda_ref}],
                "event_ids": [ev.group(1) if ev else "e"], "confidence": "high",
            })  # fmt: skip
        if "Verifier" in agent:
            return json.dumps(
                {"checks": [{"statement": "all", "verdict": "supported", "reason": ""}]}
            )
        if "Narrative" in agent:
            if '"task": "live_line"' in call.text:
                return json.dumps({"text": "The press is on: 6.4 passes per defensive action."})
            return json.dumps({"title": "A pressing masterclass",
                               "paragraphs": ["The press won it."], "key_refs": []})  # fmt: skip
        if "Personalizer" in agent:
            sent = json.loads(call.text.split("\n", 1)[1])
            texts = []
            for v in sent["variants"]:
                who = v.get("club") or v.get("player") or "the home side"
                body = f"{who}: the pressing is working well right now."
                texts.append({"persona": v["persona"], "club_id": v.get("club_id"),
                              "player_id": v.get("player_id"), "headline": f"News for {who}",
                              "body": body})  # fmt: skip
            return json.dumps({"texts": texts})
        raise AssertionError(f"unexpected agent {agent!r}")

    return FakeChatClient(reply)


def _deps(w: World, client: FakeChatClient) -> Deps:
    async def sleep(s: float) -> None:
        w.sleeps.append(s)

    return Deps(repo=w.repo, client=client, tools=StatsStub().tools(),
                facts_for=lambda _: _facts(w), sleep=sleep, langs=LANGS)  # fmt: skip


async def _run(w: World, client: FakeChatClient) -> Any:
    return await run_window(w.match_id, 1, 0.0, 300.0, _deps(w, client))


async def test_happy_path_all_verified() -> None:
    w = _world()
    report = await _run(w, _model(w))
    insights = w.repo.list_insights(w.match_id)
    assert len(insights) == 2 and all(i.verified and i.source == "agent" for i in insights)
    assert (report.insights, report.verified, report.templated) == (2, 2, 0)
    for lang in LANGS:
        texts = w.repo.list_personalized(w.match_id, lang=lang)
        assert texts and all(t.verified for t in texts)
        assert {t.persona for t in texts} == {"analyst", "casual", "club_fan"}
    assert set(w.repo.list_live_lines(w.match_id)) == {i.insight_id for i in insights}


async def test_verifier_rejection_triggers_regeneration() -> None:
    w = _world()
    whys = {1: "They allow 9.9 passes per defensive action."}  # wrong, then right
    client = _model(w, explainer=lambda n: whys.get(n, "They allow 6.4 passes per action."))
    await _run(w, client)
    insights = {i.moment_id: i for i in w.repo.list_insights(w.match_id)}
    assert all(i.verified and i.source == "agent" for i in insights.values())
    explainer_runs = [r for r in w.repo.list_match_runs(w.match_id) if r.agent == "explainer"]
    assert len(explainer_runs) == 3  # 2 moments + 1 regeneration


async def test_persistent_failure_falls_back_to_template() -> None:
    w = _world()
    client = _model(w, explainer=lambda n: f"They allow {n + 20} passes per defensive action.")
    report = await _run(w, client)
    insights = w.repo.list_insights(w.match_id)
    assert len(insights) == 2  # the UI still shows one card per moment
    assert all(i.source == "template" and i.verified for i in insights)
    assert report.templated == 2
    texts = w.repo.list_personalized(w.match_id, lang="es")
    assert texts and all(t.verified for t in texts)
    fallbacks = [r for r in w.repo.list_match_runs(w.match_id) if r.status == "fallback"]
    assert {r.moment_id for r in fallbacks} == {i.moment_id for i in insights}


async def test_429_backoff_then_success() -> None:
    w = _world()
    rate_limited = ChatClientException("Error code: 429 - Too Many Requests")
    client = _model(w, fail=lambda a, n: rate_limited if "Explainer" in a and n == 1 else None)
    report = await _run(w, client)
    assert w.sleeps == [1.0]
    assert report.verified == 2
    retried = [r for r in w.repo.list_match_runs(w.match_id) if r.status == "retry"]
    assert len(retried) == 1 and retried[0].attempts == 2


async def test_malformed_json_retry() -> None:
    w = _world()
    original = _model(w)

    def reply(call: FakeCall) -> FakeReply:
        first_try = not any("rejected" in m.text for m in call.messages)
        if "Explainer" in _agent(call) and first_try and "m001" in call.text:
            return "Sure! Here is my analysis."
        return original._reply(call)

    report = await _run(w, FakeChatClient(reply))
    assert report.verified == 2 and report.templated == 0


async def test_agent_runs_logged() -> None:
    w = _world()
    await _run(w, _model(w))
    runs = w.repo.list_match_runs(w.match_id)
    assert {r.agent for r in runs} == {"analyst", "explainer", "verifier", "narrative",
                                        "personalizer"}  # fmt: skip
    assert all(r.status == "ok" and r.tokens_in > 0 and r.latency_ms >= 0 for r in runs)
    assert all(r.moment_id and r.moment_id.startswith(w.match_id) for r in runs)


async def test_rerun_skips_what_is_done() -> None:
    w = _world()
    client = _model(w)
    await _run(w, client)
    calls = len(client.calls)
    report = await _run(w, client)
    assert len(client.calls) == calls  # nothing to do
    assert report.skipped == 2


async def test_run_match_reports() -> None:
    w = _world()
    report = await run_match(w.match_id, _deps(w, _model(w)))
    assert (report.insights, report.verified, report.templated) == (2, 2, 0)
    assert report.agent_runs > 0 and report.p95_latency_ms >= 0
    assert report.tokens_in > 0 and report.personalized == 2 * 4 * len(LANGS)
    assert w.repo.get_recap(w.match_id) is not None


def test_workflow_graph() -> None:
    w = _world()
    wf = build_workflow(_deps(w, _model(w)))
    assert [e.id for e in wf.get_executors_list()] == [
        "analyst",
        "explainer_verifier",
        "narrative",
        "personalizer_verifier",
    ]


@pytest.fixture(autouse=True)
def _quiet_warnings(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("ERROR")


async def test_report_counts_template_texts() -> None:
    w = _world()
    client = _model(w, explainer=lambda n: f"They allow {n + 20} passes per defensive action.")
    report = await _run(w, client)
    assert report.personalized == report.personalized_templated == 2 * 4 * len(LANGS)


async def test_run_match_window_limit_skips_the_recap() -> None:
    w = _world()
    report = await run_match(w.match_id, _deps(w, _model(w)), limit=1)
    assert report.insights == 2 and report.recap_source is None
    assert w.repo.get_recap(w.match_id) is None


async def test_facts_that_cannot_be_copied() -> None:
    """The workflow deep-copies messages between steps; real facts hold a database engine."""
    import os

    w = _world()

    class Uncopyable(DictFacts):
        def __init__(self, inner: DictFacts) -> None:
            self.__dict__.update(inner.__dict__)
            self.module = os  # like StatsFacts' engine: cannot be pickled or deep-copied

    deps = _deps(w, _model(w))
    deps.facts_for = lambda _: Uncopyable(_facts(w))
    report = await run_window(w.match_id, 1, 0.0, 300.0, deps)
    assert report.verified == 2


async def test_rerun_does_not_reask_the_analyst_about_passed_moments() -> None:
    w = _world()
    model = _model(w)

    def reply(call: FakeCall) -> FakeReply:
        out = model._reply(call)
        if "Tactical Analyst" in _agent(call) and isinstance(out, str):  # pass on m002
            return out.replace(
                '"moment_id": "' + w.match_id + '-m002", "surface": true',
                '"moment_id": "' + w.match_id + '-m002", "surface": false',
            )
        return out

    client = FakeChatClient(reply)
    first = await _run(w, client)
    assert first.insights == 1
    calls = len(client.calls)
    again = await _run(w, client)
    assert len(client.calls) == calls and again.skipped == 2  # one done, one passed on
