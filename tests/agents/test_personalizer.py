import json
from typing import Any

from matchmind.agents.personalizer import personalize_batch, variants_for
from matchmind.agents.runtime import PROMPT_DIR, FakeChatClient
from matchmind.engine.lineup import match_meta
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.schemas import Claim, Insight, Variant

NAMES = {"home": "Atlético Chapinero", "away": "Atlético Laureles", "p9": "Jhojan Loancia"}
PPDA = Claim(text="t", metric="ppda_10min", value=14.2, unit="",
             ref="metric:ppda_10min@2:600.0/team:home")  # fmt: skip
XG = Claim(text="t", metric="xg", value=0.41, unit="", ref="metric:xg@2:600.0/player:p9")
VARIANTS = [
    Variant(persona="analyst"),
    Variant(persona="casual"),
    Variant(persona="club_fan", club_id="home"),
    Variant(persona="club_fan", club_id="away"),
    Variant(persona="player_focus", player_id="p9"),
]


def _insight(**kw: Any) -> Insight:
    base: dict[str, Any] = {
        "insight_id": "m1-ins", "moment_id": "m1", "match_id": "x1", "level": "team",
        "headline": "Chapinero press hard", "why": "They allow 14.2 passes per action.",
        "recommendation": "Keep pressing.", "claims": [PPDA, XG], "event_ids": ["x1-e00001"],
        "confidence": "high", "verified": True, "source": "agent", "trace_id": None,
        "prompt_version": "explainer.v1",
    }  # fmt: skip
    return Insight(**{**base, **kw})


GOOD = {
    "analyst": (
        "Chapinero's press",
        "Atlético Chapinero allow 14.2 passes per defensive action (PPDA); Loancia has 0.41 xG.",
    ),
    "casual": (
        "Chapinero hunt the ball",
        "Chapinero are winning the ball back fast and giving their rivals no time.",
    ),
    "club_fan:home": (
        "Our press is biting",
        "Chapinero allow just 14.2 passes before winning it back. Keep it up!",
    ),
    "club_fan:away": (
        "Laureles under the cosh",
        "Laureles can barely string passes together against Chapinero's press.",
    ),
    "player_focus:p9": (
        "Loancia in the thick of it",
        "Jhojan Loancia has chances worth 0.41 xG so far.",
    ),
}


def _text(key: str, headline: str, body: str) -> dict[str, Any]:
    persona, _, who = key.partition(":")
    return {
        "persona": persona,
        "club_id": who if persona == "club_fan" else None,
        "player_id": who if persona == "player_focus" else None,
        "headline": headline,
        "body": body,
    }


def _reply(overrides: dict[str, tuple[str, str]] | None = None, drop: str = "") -> str:
    texts = {**GOOD, **(overrides or {})}
    return json.dumps({"texts": [_text(k, *v) for k, v in texts.items() if k != drop]})


def _client(*replies: str) -> FakeChatClient:
    it = iter(replies)
    return FakeChatClient(lambda call: next(it))


def _by_key(texts: list[Any]) -> dict[str, Any]:
    return {f"{t.persona}:{t.club_id or t.player_id or ''}".rstrip(":"): t for t in texts}


async def test_one_call_returns_every_variant() -> None:
    client = _client(_reply())
    texts = await personalize_batch(_insight(), "en", VARIANTS, client, names=NAMES)
    assert len(client.calls) == 1
    assert set(_by_key(texts)) == set(GOOD)
    assert all(t.verified is False and t.lang == "en" for t in texts)  # the Verifier decides
    assert _by_key(texts)["casual"].body == GOOD["casual"][1]


async def test_casual_has_no_jargon() -> None:
    jargon = {"casual": ("Press!", "Their PPDA is 14.2, so they press hard.")}
    client = _client(_reply(jargon), _reply())
    texts = _by_key(await personalize_batch(_insight(), "en", VARIANTS, client, names=NAMES))
    assert "PPDA" not in texts["casual"].body
    assert "PPDA" in client.calls[1].text and "casual" in client.calls[1].text


async def test_word_limits() -> None:
    long = {"casual": ("Too long", " ".join(["word"] * 60))}
    client = _client(_reply(long), _reply(long))
    texts = _by_key(await personalize_batch(_insight(), "en", VARIANTS, client, names=NAMES))
    assert len(texts["casual"].body.split()) <= 45
    assert texts["casual"].verified  # the template stands in, already verified


async def test_only_failed_variants_are_regenerated_or_templated() -> None:
    bad = {"analyst": ("Press", "They allow 19.9 passes per action.")}
    client = _client(_reply(bad), _reply(bad))
    texts = _by_key(await personalize_batch(_insight(), "en", VARIANTS, client, names=NAMES))
    second = json.loads(client.calls[1].text.split("\n", 1)[1])
    assert [v["persona"] for v in second["variants"]] == ["analyst"]
    assert "19.9" in client.calls[1].text
    assert texts["analyst"].verified  # template
    assert texts["casual"].body == GOOD["casual"][1] and not texts["casual"].verified  # agent


async def test_missing_variant_gets_a_template() -> None:
    client = _client(_reply(drop="player_focus:p9"), _reply(drop="player_focus:p9"))
    texts = _by_key(await personalize_batch(_insight(), "en", VARIANTS, client, names=NAMES))
    assert texts["player_focus:p9"].headline == "Jhojan Loancia in focus"


async def test_club_fan_must_name_its_club() -> None:
    anon = {"club_fan:away": ("Tough day", "The press is too strong today.")}
    client = _client(_reply(anon), _reply())
    texts = _by_key(await personalize_batch(_insight(), "en", VARIANTS, client, names=NAMES))
    assert "Laureles" in texts["club_fan:away"].body
    assert "Atlético Laureles" in client.calls[1].text


async def test_localized_numbers_and_rtl() -> None:
    ar = {k: (h, b) for k, (h, b) in GOOD.items()}
    ar["analyst"] = ("الضغط", "يسمح Atlético Chapinero بـ ١٤٫٢ تمريرة لكل إجراء دفاعي (PPDA).")
    texts = _by_key(await personalize_batch(_insight(), "ar", VARIANTS,
                                            _client(_reply(ar)), names=NAMES))  # fmt: skip
    assert texts["analyst"].dir == "rtl" and "١٤٫٢" in texts["analyst"].body
    assert not texts["analyst"].verified  # the agent text was kept


async def test_message_carries_rules_names_and_claims() -> None:
    client = _client(_reply())
    await personalize_batch(_insight(), "es", VARIANTS, client, names=NAMES)
    sent = json.loads(client.calls[0].text.split("\n", 1)[1])
    assert sent["lang"] == "es"
    assert sent["variants"][2] == {"persona": "club_fan", "club_id": "home",
                                   "club": "Atlético Chapinero", "max_words": 60}  # fmt: skip
    assert sent["claims"][0]["value"] == 14.2
    assert "Atlético" in client.calls[0].text  # names unescaped


def test_variants_for() -> None:
    league = build_league()
    meta = match_meta(league, build_fixtures(league, seed=2026)[0], seed=7)
    player = meta.home_squad[9].player_id
    claim = XG.model_copy(update={"ref": f"metric:xg@2:600.0/player:{player}"})
    stranger = XG.model_copy(update={"ref": "metric:xg@2:600.0/player:not-in-match"})
    variants = variants_for(_insight(claims=[PPDA, claim, claim, stranger]), meta)
    assert [(v.persona, v.club_id, v.player_id) for v in variants] == [
        ("analyst", None, None),
        ("casual", None, None),
        ("club_fan", meta.home.club_id, None),
        ("club_fan", meta.away.club_id, None),
        ("player_focus", None, player),
    ]


def test_prompt_states_the_constitution() -> None:
    text = (PROMPT_DIR / "personalizer.v1.md").read_text()
    assert "### II. Verified before visible (NON-NEGOTIABLE)" in text
    assert text.count("## Example") == 2
