import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from conftest import StatsStub, moment

from matchmind.agents.runtime import PROMPT_DIR, FakeCall, FakeChatClient
from matchmind.agents.verifier import insight_text, verify, verify_loop
from matchmind.schemas import AnalystDecision, Claim, Event, Insight

PPDA_REF = "metric:ppda_10min@2:3540.0/team:home"
POSS_REF = "metric:possession@2:3540.0/team:home"


@dataclass
class FakeFacts:
    """Stored values by ref, plus the match's minutes, scores, and events."""

    values: dict[str, float] = field(default_factory=lambda: {PPDA_REF: 14.2, POSS_REF: 0.538})
    minutes: set[int] = field(default_factory=lambda: {56, 62})
    scores: set[tuple[int, int]] = field(default_factory=lambda: {(0, 0), (1, 0), (1, 1)})
    formations: set[str] = field(default_factory=lambda: {"4-4-2"})
    names: dict[str, str] = field(default_factory=lambda: {"home": "Atlético Chapinero"})
    looked_up: list[str] = field(default_factory=list)

    def lookup(self, claim: Claim) -> float | None:
        self.looked_up.append(claim.ref)
        return self.values.get(claim.ref)

    def events(self, event_ids: list[str]) -> list[Event]:
        return [
            Event(event_id=e, match_id="x1", period=2, t=3500.0, type="tackle", team_id="home",
                  player_id="p4", x=30.0, y=30.0, end_x=None, end_y=None, outcome=True,
                  receiver_id=None, ball_speed_ms=None)
            for e in event_ids
        ]  # fmt: skip

    def third(self, event: Event) -> str:
        return "attacking"

    def before(self, event: Event) -> list[Event]:
        return [event.model_copy(update={"event_id": "x1-e00000", "type": "pass", "t": 3498.0})]


def _claim(value: float, ref: str = PPDA_REF, metric: str = "ppda_10min", unit: str = "") -> Claim:
    return Claim(text="they allow 14.2 passes", metric=metric, value=value, unit=unit, ref=ref)


def _insight(
    why: str = "By 62' they allow 14.2 passes per defensive action.", **kw: Any
) -> Insight:
    base: dict[str, Any] = {
        "insight_id": "m1-ins",
        "moment_id": "m1",
        "match_id": "x1",
        "level": "team",
        "headline": "The press switched off",
        "why": why,
        "recommendation": "Push the wide forwards up again.",
        "claims": [_claim(14.2)],
        "event_ids": ["x1-e00001"],
        "confidence": "high",
        "verified": False,
        "source": "agent",
        "trace_id": None,
        "prompt_version": "explainer.v1",
    }
    return Insight(**{**base, **kw})


def _checks(*checks: tuple[str, str, str]) -> str:
    """A Verifier reply: one (statement, verdict, reason) per statement."""
    return json.dumps(
        {"checks": [{"statement": s, "verdict": v, "reason": r} for s, v, r in checks]}
    )


def _judge(ok: bool, problems: list[str] | None = None) -> FakeChatClient:
    checks = [("The press switched off", "supported", "matches the tackle")]
    checks += [("statement", "contradicted", p) for p in problems or []]
    return FakeChatClient({"*": _checks(*checks)})


async def test_passes_correct_insight() -> None:
    insight = _insight()
    verdict = await verify(insight, "en", insight_text(insight), FakeFacts(), _judge(True))
    assert verdict.ok and verdict.failures == [] and verdict.fixed_claims == []


async def test_deterministic_failure_cannot_be_overridden() -> None:
    insight = _insight(claims=[_claim(15.0)], why="They allow 15 passes per defensive action.")
    judge = _judge(True)  # the model says everything is fine
    verdict = await verify(insight, "en", insight_text(insight), FakeFacts(), judge)
    assert not verdict.ok
    assert judge.calls == []  # numbers failed: the model is not even asked


async def test_failures_are_actionable() -> None:
    insight = _insight(claims=[_claim(15.0)], why="They allow 15 passes and won 47 duels.")
    verdict = await verify(insight, "en", insight_text(insight), FakeFacts(), _judge(True))
    wrong = next(f for f in verdict.failures if "ppda_10min" in f)
    assert "they allow 14.2 passes" in wrong and "15" in wrong and "14.2" in wrong
    assert any("'47'" in f for f in verdict.failures)
    assert verdict.fixed_claims == [_claim(14.2)]


async def test_unverifiable_ref_fails() -> None:
    insight = _insight(claims=[_claim(14.2, ref="metric:ppda_10min@2:3540.0")])
    verdict = await verify(insight, "en", insight_text(insight), FakeFacts(), _judge(True))
    assert not verdict.ok and any("unverifiable" in f for f in verdict.failures)


async def test_minutes_scores_and_formations_come_from_the_match() -> None:
    ok = _insight(why="At 62' it is 1-1 and they allow 14.2 passes in a 4-4-2.")
    assert (await verify(ok, "en", insight_text(ok), FakeFacts(), _judge(True))).ok
    bad = _insight(why="At 63' it is 2-1 and they allow 14.2 passes in a 3-5-2.")
    verdict = await verify(bad, "en", insight_text(bad), FakeFacts(), _judge(True))
    assert len(verdict.failures) == 3


async def test_percent_claim_may_scale_a_ratio() -> None:
    claim = _claim(53.8, ref=POSS_REF, metric="possession", unit="%")
    insight = _insight(claims=[claim], why="They have 53.8% of the ball.")
    assert (await verify(insight, "en", insight_text(insight), FakeFacts(), _judge(True))).ok


async def test_translated_text_is_checked_in_its_language() -> None:
    insight = _insight()
    es = "Permiten 14,2 pases por acción defensiva desde el minuto 62."
    assert (await verify(insight, "es", es, FakeFacts(), _judge(True))).ok
    bad = "Permiten quince pases por acción defensiva."
    assert not (await verify(insight, "es", bad, FakeFacts(), _judge(True))).ok


async def test_qualitative_problems_fail_the_verdict() -> None:
    insight = _insight()
    judge = _judge(False, ["The cited tackle was by the away side, not the home side."])
    verdict = await verify(insight, "en", insight_text(insight), FakeFacts(), judge)
    assert not verdict.ok and verdict.failures == [
        "qualitative: 'statement': The cited tackle was by the away side, not the home side."
    ]
    sent = judge.calls[0].text
    assert "x1-e00001" in sent and "tackle" in sent and insight.why in sent
    assert '"third": "attacking"' in sent
    sent_json = json.loads(sent.split("\n", 1)[1])
    assert sent_json["events"][0]["just_before"][0]["type"] == "pass"
    assert sent_json["facts"] == [
        {"statement": "they allow # passes", "about": "Atlético Chapinero"}
    ]
    assert "claims" not in sent_json


async def test_only_contradicted_or_invented_statements_fail() -> None:
    insight = _insight()
    lenient = _checks(("a", "supported", ""), ("b", "not_covered", "events are silent"))
    assert (await verify(insight, "en", insight_text(insight), FakeFacts(),
                         FakeChatClient({"*": lenient}))).ok  # fmt: skip
    invented = _checks(("straight after a long kick", "invented", "no kick just before"))
    verdict = await verify(insight, "en", insight_text(insight), FakeFacts(),
                           FakeChatClient({"*": invented}))  # fmt: skip
    assert verdict.failures == ["qualitative: 'straight after a long kick': no kick just before"]


async def test_an_empty_check_list_fails_closed() -> None:
    insight = _insight()
    empty = FakeChatClient({"*": json.dumps({"checks": []})})
    assert not (await verify(insight, "en", insight_text(insight), FakeFacts(), empty)).ok


async def test_verifier_runs_at_temperature_zero() -> None:
    insight = _insight()
    judge = _judge(True)
    await verify(insight, "en", insight_text(insight), FakeFacts(), judge)
    assert judge.calls[0].options.get("temperature") == 0.0


def _decision() -> AnalystDecision:
    return AnalystDecision(
        moment_id="m1",
        surface=True,
        level="team",
        priority=4,
        tactical_context="press dropped",
        metrics_to_cite=["ppda_10min"],
    )


def _explainer_and_judge(*whys: str, judge_ok: bool = True) -> FakeChatClient:
    """One fake for both agents: Explainer drafts in turn, and the Verifier's judgement."""
    drafts = iter(whys)

    def reply(call: FakeCall) -> str:
        if "You are the Verifier" in call.instructions:
            verdict = "supported" if judge_ok else "contradicted"
            return _checks(("They allow", verdict, "wrong side"))
        why = next(drafts)
        claim = _claim(14.2).model_dump()
        draft = {
            "headline": "Press off",
            "why": why,
            "recommendation": "Press again.",
            "claims": [claim],
            "event_ids": ["x1-e00001"],
            "confidence": "high",
        }
        return json.dumps(draft)

    return FakeChatClient(reply)


async def test_loop_regenerates_with_the_failures(stats: StatsStub) -> None:
    client = _explainer_and_judge("They allow 15 passes.", "They allow 14.2 passes.")
    seen: list[tuple[str, bool]] = []
    insight = await verify_loop(
        _decision(), moment(1), client, stats.tools(), FakeFacts(),
        on_attempt=lambda i, v: seen.append((i.why, v.ok)),
    )  # fmt: skip
    assert seen == [("They allow 15 passes.", False), ("They allow 14.2 passes.", True)]
    assert insight is not None and insight.verified and insight.why == "They allow 14.2 passes."
    second_draft = [c for c in client.calls if "You are the Verifier" not in c.instructions][1]
    assert "'15'" in second_draft.text  # the Verifier's failure was fed back


async def test_loop_gives_up_after_two_regenerations(stats: StatsStub) -> None:
    client = _explainer_and_judge("15 passes.", "16 passes.", "17 passes.", "18 passes.")
    insight = await verify_loop(_decision(), moment(1), client, stats.tools(), FakeFacts())
    assert insight is None
    drafts = [c for c in client.calls if "You are the Verifier" not in c.instructions]
    assert len(drafts) == 3  # first try + 2 regenerations


def test_prompt_states_the_constitution() -> None:
    text = (PROMPT_DIR / "verifier.v1.md").read_text()
    assert "### II. Verified before visible (NON-NEGOTIABLE)" in text
    assert text.count("## Example") == 2


@pytest.mark.parametrize("lang", ["en", "es", "pt", "fr", "ar"])
def test_insight_text_is_the_three_fields(lang: str) -> None:
    text = insight_text(_insight())
    assert "The press switched off" in text and "Push the wide" in text


async def test_a_half_named_for_the_future_is_not_flagged_by_code() -> None:
    """Which half a moment is in is the Verifier agent's call: "extend the lead in the second
    half" is advice about later, not a wrong half (a phrase match flagged it, live)."""
    insight = _insight()  # its cited events are in the second half
    text = "They allow 14.2 passes. Hold this shape until the end of the first half."
    judge = _judge(True)
    assert (await verify(insight, "en", text, FakeFacts(), judge)).ok and judge.calls


@dataclass
class LeadFacts(FakeFacts):
    """Facts that know the score at the insight's moment (TASK-24.4)."""

    score: dict[str, int] = field(default_factory=lambda: {"home": 1, "away": 1})

    def lead_context(self, moment_id: str) -> tuple[dict[str, list[str]], dict[str, int]] | None:
        return {"home": ["chapinero"], "away": ["laureles"]}, self.score


async def test_a_lead_claim_the_score_contradicts_fails_before_the_model() -> None:
    insight = _insight(headline="Morejo gives Chapinero the lead")
    judge = _judge(True)
    verdict = await verify(insight, "en", insight_text(insight), LeadFacts(), judge)
    assert not verdict.ok and "1–1" in verdict.failures[0]
    assert judge.calls == []  # deterministic, like the numbers
    ahead = LeadFacts(score={"home": 2, "away": 1})
    assert (await verify(insight, "en", insight_text(insight), ahead, _judge(True))).ok
