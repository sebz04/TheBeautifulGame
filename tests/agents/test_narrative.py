import json
from typing import Any

from matchmind.agents.narrative import MAX_LINE, RecapContext, live_line, recap
from matchmind.agents.runtime import PROMPT_DIR, FakeChatClient
from matchmind.schemas import Claim, Insight

PPDA = Claim(text="they allow 9.0 passes", metric="ppda_10min", value=9.0, unit="",
             ref="metric:ppda_10min@1:1200.0/team:away")  # fmt: skip
XG = Claim(text="0.41 xG", metric="xg", value=0.409, unit="", ref="metric:xg@1:2800.0/player:p9")


def _insight(claims: list[Claim] | None = None, **kw: Any) -> Insight:
    base: dict[str, Any] = {
        "insight_id": "m1-ins", "moment_id": "m1", "match_id": "x1", "level": "team",
        "headline": "Laureles' press collapses", "why": "They allow 9.0 passes per action.",
        "recommendation": "Press higher.", "claims": claims if claims is not None else [PPDA],
        "event_ids": ["x1-e00001"], "confidence": "high", "verified": True,
        "source": "agent", "trace_id": None, "prompt_version": "explainer.v1",
    }  # fmt: skip
    return Insight(**{**base, **kw})


def _line(text: str) -> str:
    return json.dumps({"text": text})


def _replies(*texts: str) -> FakeChatClient:
    it = iter(texts)
    return FakeChatClient(lambda call: next(it))


# --- live lines -----------------------------------------------------------------------


async def test_live_line_respects_the_length_limit() -> None:
    long = "Laureles " + "really " * 30 + "lost their press."
    client = _replies(_line(long), _line("Laureles' press fades: 9.0 passes per action."))
    line = await live_line(_insight(), [], client)
    assert line == "Laureles' press fades: 9.0 passes per action." and len(line) <= MAX_LINE
    assert str(MAX_LINE) in client.calls[1].text and "characters" in client.calls[1].text


async def test_live_line_numbers_must_be_claims() -> None:
    client = _replies(_line("Laureles allow 12 passes."), _line("Laureles allow 9.0 passes."))
    assert await live_line(_insight(), [], client) == "Laureles allow 9.0 passes."
    assert "'12'" in client.calls[1].text


async def test_live_line_may_quote_a_milestone() -> None:
    milestone = "50th appearance for Atlético Laureles (round 8)"
    client = _replies(_line("Balero, on his 50th appearance, sees the press fade: 9.0."))
    line = await live_line(_insight(), [milestone], client)
    assert "50th" in line
    assert milestone in client.calls[0].text


async def test_live_line_falls_back_to_the_headline() -> None:
    client = _replies(_line("Laureles allow 12 passes."), _line("x" * 200))
    assert await live_line(_insight(), [], client) == "Laureles' press collapses"
    long_headline = _insight(headline="A" * 200)
    client = _replies(_line("y" * 200), _line("z" * 200))
    assert len(await live_line(long_headline, [], client)) <= MAX_LINE


# --- recap ----------------------------------------------------------------------------


def _ctx() -> RecapContext:
    return RecapContext(
        match_id="x1", home="Atlético Chapinero", away="Atlético Laureles", score=(2, 1),
        goals=[("45+2'", "Mateo Balero", "Atlético Laureles"),
               ("63'", "Harold Morejo", "Atlético Chapinero"),
               ("86'", "Harold Morejo", "Atlético Chapinero")],
        cards=[("56'", "Jhojan Loancia", "Atlético Chapinero")],
        milestones=["Atlético Chapinero: first comeback win of the season"],
        minutes={47, 56, 63, 86}, scores={(0, 0), (0, 1), (1, 1), (2, 1)},
    )  # fmt: skip


def _recap_reply(
    paragraphs: list[str], refs: list[str], title: str = "Chapinero turn it around"
) -> str:
    return json.dumps({"title": title, "paragraphs": paragraphs, "key_refs": refs})


async def test_recap_numbers_are_cited_claims() -> None:
    insights = [_insight(), _insight([XG], insight_id="m2-ins", moment_id="m2")]
    good = _recap_reply(
        ["Ten-man Chapinero won 2-1 after Morejo scored at 63' and 86'.",
         "Laureles' press had faded: 9.0 passes per defensive action."],
        [PPDA.ref],
    )  # fmt: skip
    r = await recap(_ctx(), insights, _replies(good))
    assert r.source == "agent" and r.verified
    assert r.key_numbers == [PPDA]
    assert r.title == "Chapinero turn it around"


async def test_recap_number_not_cited_is_regenerated() -> None:
    insights = [_insight(), _insight([XG], insight_id="m2-ins", moment_id="m2")]
    uncited = _recap_reply(["Balero's chances were worth 0.41 xG."], [PPDA.ref])  # XG not cited
    cited = _recap_reply(["Balero's chances were worth 0.41 xG."], [XG.ref])
    client = _replies(uncited, cited)
    r = await recap(_ctx(), insights, client)
    assert r.source == "agent" and r.key_numbers == [XG]
    assert "0.41" in client.calls[1].text


async def test_recap_unknown_ref_is_rejected() -> None:
    bad = _recap_reply(["A 2-1 win."], ["metric:made_up@1:1.0/team:home"])
    client = _replies(bad, bad)
    r = await recap(_ctx(), [_insight()], client)
    assert r.source == "template"
    assert "made_up" in client.calls[1].text


async def test_recap_falls_back_to_a_template_with_score_and_goals() -> None:
    bad = _recap_reply(["They won 3-0 with 99 shots."], [])
    r = await recap(_ctx(), [_insight()], _replies(bad, bad))
    assert r.source == "template" and r.verified
    text = " ".join([r.title, *r.paragraphs])
    assert "2-1" in text and "Harold Morejo" in text and "86'" in text and "56'" in text
    assert r.key_numbers == [PPDA]


async def test_recap_message_has_score_goals_and_milestones() -> None:
    good = _recap_reply(["Chapinero won 2-1."], [])
    client = _replies(good)
    await recap(_ctx(), [_insight()], client)
    sent = json.loads(client.calls[0].text.split("\n", 1)[1])
    assert sent["score"] == "Atlético Chapinero 2-1 Atlético Laureles"
    assert sent["goals"][0] == {
        "minute": "45+2'",
        "player": "Mateo Balero",
        "team": "Atlético Laureles",
    }
    assert sent["milestones"] == ["Atlético Chapinero: first comeback win of the season"]
    assert sent["claims"][0]["ref"] == PPDA.ref


def test_prompt_states_the_constitution() -> None:
    text = (PROMPT_DIR / "narrative.v1.md").read_text()
    assert "### I. Code computes, agents interpret (NON-NEGOTIABLE)" in text
    assert text.count("## Example") == 2


def test_only_milestones_from_earlier_rounds() -> None:
    from matchmind.agents.narrative import milestones_before

    items = [
        "Balero: first league goal of the season vs Chapinero (round 1)",
        "Balero: 25th goal for Laureles (round 6)",
        "Laureles: top of the table",  # no round: timing unknown
        "Morejo: 50th appearance (round 3)",
    ]
    assert milestones_before(items, 4) == [items[0], items[3]]
    assert milestones_before(items, 1) == []
