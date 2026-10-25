import json
from typing import Any

import pytest
from conftest import StatsStub, moment

from matchmind.agents.explainer import ExplainerError, explain
from matchmind.agents.runtime import PROMPT_DIR, FakeCall, FakeChatClient, FakeReply, tool_call
from matchmind.schemas import AnalystDecision


def _decision(level: str = "team") -> AnalystDecision:
    return AnalystDecision(
        moment_id="m1",
        surface=True,
        level=level,  # type: ignore[arg-type]
        priority=4,
        tactical_context="The home side stopped pressing after the substitution.",
        metrics_to_cite=["ppda_10min"],
    )


def _draft(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "headline": "The press switched off",
        "why": "After the change the home side let the centre-backs carry the ball forward.",
        "recommendation": "Push the wide forwards up again to stop the easy first pass.",
        "claims": [
            {
                "text": "Their PPDA rose to 14.2",
                "metric": "ppda_10min",
                "value": 14.2,
                "unit": "",
                "ref": "metric:ppda_10min@2:3540.0/team:home",
            }
        ],
        "event_ids": ["x1-e00001"],
        "confidence": "high",
    }
    return {**base, **overrides}


def _client(
    *drafts: dict[str, Any], look_up: list[tuple[str, dict[str, Any]]] = ()
) -> FakeChatClient:  # type: ignore[assignment]
    """A fake explainer: makes the given tool calls, then returns the drafts in turn."""
    replies = iter(drafts)

    def reply(call: FakeCall) -> FakeReply:
        if look_up and not call.tool_results:
            return [tool_call(name, **args) for name, args in look_up]
        return json.dumps(next(replies))

    return FakeChatClient(reply)


async def test_explainer_output_has_claims_and_refs(stats: StatsStub) -> None:
    client = _client(_draft(), look_up=[("get_moment", {"moment_id": "m1"})])
    insight = await explain(_decision(), moment(1), client, stats.tools())
    assert insight.claims and all(c.ref for c in insight.claims)
    assert insight.event_ids == ["x1-e00001"]
    assert (insight.moment_id, insight.match_id, insight.level) == ("m1", "x1", "team")
    assert insight.source == "agent" and insight.verified is False
    assert insight.prompt_version == "explainer.v1"


async def test_explainer_rejects_insight_without_event_ids(stats: StatsStub) -> None:
    client = _client(_draft(event_ids=[]), _draft())
    insight = await explain(_decision(), moment(1), client, stats.tools())
    assert insight.event_ids == ["x1-e00001"]
    assert len(client.calls) == 2
    assert "event_ids" in client.calls[1].text  # the error is fed back


async def test_explainer_gives_up_after_one_regeneration(stats: StatsStub) -> None:
    client = _client(_draft(event_ids=[]), _draft(claims=[]))
    with pytest.raises(ExplainerError, match="m1"):
        await explain(_decision(), moment(1), client, stats.tools())
    assert len(client.calls) == 2


async def test_claim_without_ref_is_rejected(stats: StatsStub) -> None:
    claim = {**_draft()["claims"][0], "ref": " "}
    client = _client(_draft(claims=[claim]), _draft())
    await explain(_decision(), moment(1), client, stats.tools())
    assert "ref" in client.calls[1].text


async def test_counterfactual_claim_must_cite_get_counterfactual(stats: StatsStub) -> None:
    cf_claim = {
        "text": "A pass to the far post was worth more",
        "metric": "counterfactual_gain",
        "value": 0.031,
        "unit": "xT",
        "ref": "x1-e00001",
    }
    unchecked = _client(_draft(claims=[cf_claim]), _draft())
    await explain(_decision(), moment(1), unchecked, stats.tools())
    assert "get_counterfactual" in unchecked.calls[-1].text  # sent back once

    checked = _client(
        _draft(claims=[cf_claim]), look_up=[("get_counterfactual", {"event_id": "x1-e00001"})]
    )
    insight = await explain(_decision(), moment(1), checked, stats.tools())
    assert insight.claims[0].metric == "counterfactual_gain"


@pytest.mark.parametrize(
    ("level", "question"),
    [
        ("team", "What should they do?"),
        ("player", "What should they do?"),
        ("game", "What to watch next"),
    ],
)
async def test_recommendation_question_follows_the_level(
    stats: StatsStub, level: str, question: str
) -> None:
    client = _client(_draft())
    insight = await explain(_decision(level), moment(1), client, stats.tools())
    assert question in client.calls[0].text
    assert insight.level == level


async def test_explainer_sees_the_decision_and_moment(stats: StatsStub) -> None:
    client = _client(_draft())
    await explain(_decision(), moment(1, kind="pressing_collapse"), client, stats.tools())
    text = client.calls[0].text
    assert "stopped pressing" in text and "ppda_10min" in text and "pressing_collapse" in text
    assert "Verified before visible" in client.calls[0].instructions


async def test_insight_carries_the_trace_id(stats: StatsStub) -> None:
    from opentelemetry.sdk.trace import TracerProvider

    tracer = TracerProvider().get_tracer("t")
    insight = await explain(_decision(), moment(1), _client(_draft()), stats.tools(), tracer=tracer)
    assert insight.trace_id is not None and len(insight.trace_id) == 32


def test_prompt_states_the_constitution() -> None:
    text = (PROMPT_DIR / "explainer.v1.md").read_text()
    assert "### I. Code computes, agents interpret (NON-NEGOTIABLE)" in text
    assert "### II. Verified before visible (NON-NEGOTIABLE)" in text
    assert text.count("## Example") == 2


async def test_reply_that_is_not_json_is_regenerated(stats: StatsStub) -> None:
    replies = iter(["Sure! Here is the insight.", json.dumps(_draft())])
    client = FakeChatClient(lambda call: next(replies))
    insight = await explain(_decision(), moment(1), client, stats.tools())
    assert insight.headline == "The press switched off"


async def test_service_errors_are_not_swallowed(stats: StatsStub) -> None:
    from agent_framework.exceptions import ChatClientException

    def reply(call: FakeCall) -> FakeReply:
        raise ChatClientException("429 Too Many Requests")

    with pytest.raises(ChatClientException, match="429"):
        await explain(_decision(), moment(1), FakeChatClient(reply), stats.tools())


async def test_explainer_gets_names_and_minute_labels(stats: StatsStub) -> None:
    client = _client(_draft())
    m = moment(1, period=2, t_start=600.0, t_end=638.5)
    await explain(_decision(), m, client, stats.tools(), names={"home": "Atlético Chapinero"})
    sent = json.loads(client.calls[0].text.split("\n", 1)[1])
    assert sent["names"] == {"home": "Atlético Chapinero"}
    assert sent["moment"]["minute_end"] == "56'"


async def test_explainer_runs_at_temperature_zero(stats: StatsStub) -> None:
    client = _client(_draft())
    await explain(_decision(), moment(1), client, stats.tools())
    assert client.calls[0].options.get("temperature") == 0.0


async def test_insight_keeps_at_most_eight_key_events(stats: StatsStub) -> None:
    from matchmind.agents.explainer import MAX_EVENTS

    cited = [f"x1-e{i:05d}" for i in range(50, 100)]
    cf = {"text": "t", "metric": "counterfactual_gain", "value": 0.03, "unit": "xT",
          "ref": "x1-e00077"}  # fmt: skip
    draft = _draft(event_ids=[*cited, "x1-e00001"], claims=[*_draft()["claims"], cf])
    look = [("get_counterfactual", {"event_id": "x1-e00077"})]
    insight = await explain(_decision(), moment(1), _client(draft, look_up=look), stats.tools())
    assert MAX_EVENTS == 8 and len(insight.event_ids) == 8
    assert insight.event_ids[:2] == ["x1-e00001", "x1-e00077"]  # the moment's, then the claims'
    assert insight.event_ids[2:] == cited[:6] and len(set(insight.event_ids)) == 8
