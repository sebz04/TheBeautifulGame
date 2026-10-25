import json
from typing import Any

from conftest import StatsStub, moment

from matchmind.agents.analyst import analyze, batches
from matchmind.agents.runtime import PROMPT_DIR, FakeCall, FakeChatClient, FakeReply, tool_call


def _decision(i: int, surface: bool, priority: int = 3) -> dict[str, Any]:
    return {
        "moment_id": f"m{i}",
        "surface": surface,
        "level": "team",
        "priority": priority,
        "tactical_context": "The press broke down after the substitution.",
        "metrics_to_cite": ["ppda"],
    }


def _analyst(decisions: list[dict[str, Any]], look_up: list[str]) -> FakeChatClient:
    """A fake analyst: looks up the given moments first, then returns the decisions."""

    def reply(call: FakeCall) -> FakeReply:
        if not call.tool_results and look_up:
            return [tool_call("get_moment", moment_id=m) for m in look_up]
        return json.dumps({"decisions": decisions})

    return FakeChatClient(reply)


async def test_analyst_filters_low_priority(stats: StatsStub) -> None:
    moments = [moment(1), moment(2), moment(3)]
    client = _analyst([_decision(1, True), _decision(2, False), _decision(3, True)], ["m1", "m3"])
    decisions = await analyze(moments, client, stats.tools())
    assert [d.moment_id for d in decisions] == ["m1", "m3"]
    assert all(d.surface for d in decisions)


async def test_analyst_looks_up_every_surfaced_moment(stats: StatsStub) -> None:
    client = _analyst([_decision(1, True), _decision(2, True)], ["m1", "m2"])
    await analyze([moment(1), moment(2)], client, stats.tools())
    assert {args["moment_id"] for name, args in stats.calls if name == "get_moment"} == {"m1", "m2"}


async def test_unlooked_moment_is_retried_then_dropped(stats: StatsStub) -> None:
    client = _analyst([_decision(1, True), _decision(2, True)], ["m1"])
    decisions = await analyze([moment(1), moment(2)], client, stats.tools())
    assert [d.moment_id for d in decisions] == ["m1"]
    assert len([c for c in client.calls if not c.tool_results]) == 2  # one retry
    assert "m2" in client.calls[-1].text  # the retry names the moment it skipped


async def test_a_call_in_the_moment_window_counts_as_looking_it_up(stats: StatsStub) -> None:
    m = moment(1, t_start=600.0, t_end=640.0)

    def reply(call: FakeCall) -> FakeReply:
        if not call.tool_results:
            args = {"match_id": "x1", "team_id": "home", "period": 1, "t": 640.0}
            return [tool_call("get_team_metrics", **args)]
        return json.dumps({"decisions": [_decision(1, True)]})

    assert len(await analyze([m], FakeChatClient(reply), stats.tools())) == 1


async def test_decisions_for_unknown_moments_are_ignored(stats: StatsStub) -> None:
    client = _analyst([_decision(1, True), _decision(9, True)], ["m1", "m9"])
    decisions = await analyze([moment(1)], client, stats.tools())
    assert [d.moment_id for d in decisions] == ["m1"]


async def test_surfaced_moments_come_back_by_priority(stats: StatsStub) -> None:
    decisions_in = [_decision(1, True, priority=2), _decision(2, True, priority=5)]
    client = _analyst(decisions_in, ["m1", "m2"])
    out = await analyze([moment(1), moment(2)], client, stats.tools())
    assert [d.moment_id for d in out] == ["m2", "m1"]


async def test_analyst_sees_the_moments(stats: StatsStub) -> None:
    client = _analyst([_decision(1, False)], [])
    await analyze([moment(1, kind="red_card")], client, stats.tools())
    sent = json.loads(client.calls[0].text.split("\n", 1)[1])
    assert sent["moments"][0]["moment_id"] == "m1" and sent["moments"][0]["kind"] == "red_card"
    assert "Code computes, agents interpret" in client.calls[0].instructions


def test_batches_cover_five_match_minutes() -> None:
    moments = [moment(i) for i in range(12)]  # one a minute, all in period 1
    groups = batches(moments, minutes=5)
    assert [[m.moment_id for m in g] for g in groups] == [
        ["m0", "m1", "m2", "m3", "m4"],
        ["m5", "m6", "m7", "m8", "m9"],
        ["m10", "m11"],
    ]
    second_half = moment(1, period=2)
    assert len(batches([moment(1), second_half])) == 2


def test_prompt_states_the_constitution() -> None:
    text = (PROMPT_DIR / "analyst.v1.md").read_text()
    assert "### I. Code computes, agents interpret (NON-NEGOTIABLE)" in text
    assert "### II. Verified before visible (NON-NEGOTIABLE)" in text
    assert text.count("## Example") == 2


async def test_malformed_reply_is_retried_once(stats: StatsStub) -> None:
    replies = iter(
        ['{"decisions": [{"moment_id": "m1"}]}', json.dumps({"decisions": [_decision(1, True)]})]
    )

    def reply(call: FakeCall) -> FakeReply:
        if not call.tool_results:
            return [tool_call("get_moment", moment_id="m1")]
        return next(replies)

    client = FakeChatClient(reply)
    assert [d.moment_id for d in await analyze([moment(1)], client, stats.tools())] == ["m1"]
    assert "rejected" in client.calls[-1].text


async def test_two_malformed_replies_surface_nothing(stats: StatsStub) -> None:
    client = FakeChatClient({"*": '{"decisions": [{"moment_id": "m1", "priority": 9}]}'})
    assert await analyze([moment(1)], client, stats.tools()) == []


async def test_analyst_gets_names_and_minute_labels(stats: StatsStub) -> None:
    client = _analyst([_decision(1, False)], [])
    await analyze([moment(1)], client, stats.tools(), names={"home": "Atlético Chapinero"})
    sent = json.loads(client.calls[0].text.split("\n", 1)[1])
    assert sent["names"] == {"home": "Atlético Chapinero"}
    assert sent["moments"][0]["minute_end"] == "2'"
