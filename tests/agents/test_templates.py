from itertools import product
from typing import Any

import pytest

from matchmind.agents.numbers import check_text
from matchmind.agents.templates import JARGON, WORD_LIMITS, jargon_in, render, word_count
from matchmind.schemas import Claim, Insight, Variant

LANGS = ["en", "es", "pt", "fr", "ar"]
NAMES = {"home": "Atlético Chapinero", "away": "Atlético Laureles", "p9": "Jhojan Loancia"}
VARIANTS = [
    Variant(persona="analyst"),
    Variant(persona="casual"),
    Variant(persona="club_fan", club_id="home"),
    Variant(persona="player_focus", player_id="p9"),
]


def _claim(metric: str, value: float, scope: str = "team:home", unit: str = "") -> Claim:
    return Claim(text=metric, metric=metric, value=value, unit=unit,
                 ref=f"metric:{metric}@2:600.0/{scope}")  # fmt: skip


def _insight(**kw: Any) -> Insight:
    base: dict[str, Any] = {
        "insight_id": "m1-ins", "moment_id": "m1", "match_id": "x1", "level": "team",
        "headline": "Press off", "why": "w", "recommendation": "r",
        "claims": [
            _claim("ppda_10min", 14.2),
            _claim("possession", 0.538, unit="%"),
            _claim("field_tilt_10min", 0.722, "team:away", "%"),
            _claim("xg", 0.409, "player:p9"),
            _claim("players", 10.0),
            Claim(text="g", metric="counterfactual_gain", value=0.031, unit="xT", ref="x1-e00001"),
        ],
        "event_ids": ["x1-e00001"], "confidence": "high", "verified": True,
        "source": "agent", "trace_id": None, "prompt_version": "explainer.v1",
    }  # fmt: skip
    return Insight(**{**base, **kw})


CASES = list(product(LANGS, VARIANTS))


@pytest.mark.parametrize(("lang", "variant"), CASES, ids=lambda x: getattr(x, "persona", x))
def test_template_all_langs(lang: str, variant: Variant) -> None:
    insight = _insight()
    text = render(insight, variant, lang, NAMES)  # type: ignore[arg-type]
    assert text.headline.strip() and text.body.strip()
    assert (text.persona, text.lang, text.verified) == (variant.persona, lang, True)
    assert (text.club_id, text.player_id) == (variant.club_id, variant.player_id)
    check = check_text(f"{text.headline}\n{text.body}", lang, insight.claims,  # type: ignore[arg-type]
                       lambda c: c.value)  # fmt: skip
    assert check.ok, (lang, variant.persona, check.failures, text.body)


@pytest.mark.parametrize(("lang", "variant"), CASES, ids=lambda x: getattr(x, "persona", x))
def test_template_word_limits_and_jargon(lang: str, variant: Variant) -> None:
    text = render(_insight(), variant, lang, NAMES)  # type: ignore[arg-type]
    limit = WORD_LIMITS[variant.persona]
    assert word_count(f"{text.headline} {text.body}") <= limit
    if variant.persona == "casual":
        assert not jargon_in(f"{text.headline} {text.body}")


def test_arabic_template_rtl_marker() -> None:
    assert render(_insight(), VARIANTS[0], "ar", NAMES).dir == "rtl"
    assert render(_insight(), VARIANTS[0], "en", NAMES).dir == "ltr"


def test_arabic_uses_arabic_digits() -> None:
    body = render(_insight(), VARIANTS[0], "ar", NAMES).body
    assert "١٤٫٢" in body and "14.2" not in body


def test_decimal_comma_languages() -> None:
    for lang in ("es", "pt", "fr"):
        assert "14,2" in render(_insight(), VARIANTS[0], lang, NAMES).body  # type: ignore[arg-type]


def test_club_fan_leads_with_their_club() -> None:
    away = Variant(persona="club_fan", club_id="away")
    body = render(_insight(), away, "en", NAMES).body
    assert body.index("Atlético Laureles") < body.index("Atlético Chapinero")
    assert "Atlético Laureles" in render(_insight(), away, "en", NAMES).headline


def test_player_focus_leads_with_the_player() -> None:
    text = render(_insight(), VARIANTS[3], "en", NAMES)
    assert "Jhojan Loancia" in text.headline
    assert text.body.index("0.41") < text.body.index("14.2")  # his stat comes first


def test_insight_without_claims_still_renders() -> None:
    for lang, variant in CASES:
        text = render(_insight(claims=[]), variant, lang, NAMES)  # type: ignore[arg-type]
        assert text.headline and text.body


def test_jargon_detection() -> None:
    assert jargon_in("Their PPDA rose") == ["PPDA"]
    assert jargon_in("their field tilt grew") == ["field tilt"]
    assert jargon_in("what happens next") == []  # "xT" only as its own word
    assert set(JARGON) == {"xT", "PPDA", "field tilt", "pitch control"}
