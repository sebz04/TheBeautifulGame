import pytest

from matchmind.agents.numbers import check_text, extract_numbers
from matchmind.schemas import Claim


def _values(text: str, lang: str) -> list[tuple[float, str | None]]:
    return [(n.value, n.unit) for n in extract_numbers(text, lang)]  # type: ignore[arg-type]


def _claim(value: float, unit: str = "", metric: str = "m", ref: str = "metric:m@1:600.0") -> Claim:
    return Claim(text="", metric=metric, value=value, unit=unit, ref=ref)


def _verified(claim: Claim) -> float | None:
    return claim.value


# --- extraction -----------------------------------------------------------------------


def test_extract_es_decimal_comma() -> None:
    assert _values("Recorrió 1,5 km", "es") == [(1.5, "km")]


def test_extract_fr_thousands() -> None:
    assert _values("12 000 spectateurs", "fr") == [(12000.0, None)]
    assert _values("12 000 spectateurs", "fr") == [(12000.0, None)]


def test_extract_ar_digits() -> None:
    assert _values("سجل ١٢ تسديدة", "ar") == [(12.0, None)]
    assert _values("٣٫٥ كم", "ar") == [(3.5, "km")]


def test_extract_word_numbers() -> None:
    assert _values("doce pases", "es") == [(12.0, None)]
    assert _values("onze passes", "pt") == [(11.0, None)]
    assert _values("dix-sept duels", "fr") == [(17.0, None)]
    assert _values("Seven shots", "en") == [(7.0, None)]
    assert _values("ثلاثة عشر تمريرة", "ar") == [(13.0, None)]
    assert _values("Dieciséis centros", "es") == [(16.0, None)]


def test_one_words_are_articles_not_numbers() -> None:
    assert _values("un pase y una falta", "es") == []
    assert _values("one of the best", "en") == []


@pytest.mark.parametrize(
    ("text", "lang", "value"),
    [
        ("12.000", "es", 12000.0),
        ("12.000", "pt", 12000.0),
        ("12,000", "en", 12000.0),
        ("1,500", "fr", 1.5),
        ("1.5", "es", 1.5),  # a stray decimal point is still a decimal
        ("1.5", "en", 1.5),
        ("١٢٬٠٠٠", "ar", 12000.0),
    ],
)
def test_separators_follow_the_language(text: str, lang: str, value: float) -> None:
    assert _values(text, lang) == [(value, None)]


def test_units() -> None:
    assert _values("62% possession", "en") == [(62.0, "%")]
    assert _values("un 62 % de posesión", "es") == [(62.0, "%")]
    assert _values("disparo a 104 km/h", "es") == [(104.0, "km/h")]
    assert _values("8.9 m/s", "en") == [(8.9, "m/s")]


def test_minute_marks_and_scores() -> None:
    assert _values("in the 62nd minute", "en") == [(62.0, "minute")]
    assert _values("at 62'", "en") == [(62.0, "minute")]
    assert _values("al minuto 62", "es") == [(62.0, "minute")]
    assert _values("à la 62e minute", "fr") == [(62.0, "minute")]
    assert _values("90+3'", "en") == [(93.0, "minute")]
    assert _values("في الدقيقة ٦٢", "ar") == [(62.0, "minute")]
    scores = extract_numbers("now 2-1, then 2 a 2", "es")
    assert [(n.pair, n.unit) for n in scores] == [((2, 1), "score"), ((2, 2), "score")]


def test_spans_point_at_the_number() -> None:
    text = "Corrió 1,5 km"
    (n,) = extract_numbers(text, "es")
    assert text[n.span[0] : n.span[1]] == "1,5"
    assert n.decimals == 1


# --- checking -------------------------------------------------------------------------


def test_check_accepts_matching_numbers() -> None:
    claims = [_claim(0.62, "%", metric="possession"), _claim(11.6, "km", metric="distance")]
    check = check_text("62% of the ball; he ran 11.6 km.", "en", claims, _verified)
    assert check.ok, check.failures


def test_check_flags_invented_number() -> None:
    check = check_text("He completed 47 passes.", "en", [_claim(41.0)], _verified)
    assert not check.ok
    assert any("47" in f for f in check.failures)


def test_check_flags_localized_invented_number() -> None:
    for text, lang in [("doce pases", "es"), ("١٢ تمريرة", "ar"), ("12.000 m", "es")]:
        assert not check_text(text, lang, [_claim(41.0)], _verified).ok, text


def test_check_matches_localized_values() -> None:
    claims = [_claim(1.5, "km"), _claim(12.0)]
    assert check_text("Recorrió 1,5 km y dio doce pases", "es", claims, _verified).ok
    assert check_text("قطع ١٫٥ كم و١٢ تمريرة", "ar", claims, _verified).ok


def test_check_allows_rounding_to_the_written_precision() -> None:
    assert check_text("11.6 km", "en", [_claim(11.63, "km")], _verified).ok
    assert check_text("12 sprints", "en", [_claim(11.6)], _verified).ok
    assert not check_text("12.0 sprints", "en", [_claim(11.6)], _verified).ok


def test_check_converts_units() -> None:
    assert check_text("a 104 km/h strike", "en", [_claim(28.9, "m/s")], _verified).ok
    assert check_text("11,600 m", "en", [_claim(11.6, "km")], _verified).ok


def test_check_allows_minute_mark() -> None:
    assert check_text("In the 62nd minute he scored.", "en", [], _verified, minutes={62}).ok
    bad = check_text("In the 63rd minute he scored.", "en", [], _verified, minutes={62})
    assert not bad.ok and any("minute" in f for f in bad.failures)


def test_check_allows_scoreline() -> None:
    assert check_text("It is 2-1 now.", "en", [], _verified, scores={(2, 1)}).ok
    assert check_text("Ahora 1-2.", "es", [], _verified, scores={(2, 1)}).ok
    assert not check_text("It is 3-1 now.", "en", [], _verified, scores={(2, 1)}).ok


def test_check_flags_unverifiable_and_wrong_claims() -> None:
    claim = _claim(41.0)
    missing = check_text("41 passes", "en", [claim], lambda c: None)
    assert not missing.ok and any("unverifiable" in f for f in missing.failures)
    wrong = check_text("41 passes", "en", [claim], lambda c: 38.0)
    assert not wrong.ok and any("38" in f for f in wrong.failures)


def test_claim_compared_at_its_own_precision() -> None:
    claim = _claim(0.62, "%")
    assert check_text("", "en", [claim], lambda c: 0.6213).ok
    for stored in (0.2, 0.58):
        assert not check_text("", "en", [claim], lambda c, s=stored: s).ok, stored
    assert check_text("", "en", [_claim(41.0)], lambda c: 41.4).ok


def test_formations_are_one_token() -> None:
    (n,) = extract_numbers("switched to a 4-2-3-1", "en")
    assert (n.unit, n.formation) == ("formation", "4-2-3-1")
    assert check_text("now a 4-4-2", "en", [], _verified, formations={"4-4-2"}).ok
    assert not check_text("now a 3-5-2", "en", [], _verified, formations={"4-4-2"}).ok


def test_unmatched_number_failure_quotes_its_context() -> None:
    text = "Balero has 0.409 xG from 5 shots, a fine half."
    check = check_text(text, "en", [_claim(0.409)], _verified)
    (failure,) = check.failures
    assert "'5'" in failure and "from 5 shots" in failure


def test_window_length_of_a_cited_window_metric_is_allowed() -> None:
    ppda = Claim(text="t", metric="ppda_10min", value=9.0, unit="", ref="r")
    assert check_text("9.0 passes per action over the last 10 minutes", "en", [ppda], _verified).ok
    assert check_text("٩٫٠ تمريرة في آخر ١٠ دقائق", "ar", [ppda], _verified).ok
    momentum = Claim(text="t", metric="momentum", value=0.33, unit="", ref="r")
    assert check_text("0.33 over the last 5 minutes", "en", [momentum], _verified).ok
    plain = Claim(text="t", metric="possession", value=0.58, unit="%", ref="r")
    assert not check_text("58% in the last 10 minutes", "en", [plain], _verified).ok


def test_window_length_matches_only_exactly() -> None:
    ppda = Claim(text="t", metric="ppda_10min", value=6.4, unit="", ref="r")
    assert not check_text("They allow 9.9 passes per action.", "en", [ppda], _verified).ok
    assert not check_text("They allow 10.0 passes per action.", "en", [ppda], _verified).ok


def test_minute_ranges() -> None:
    assert _values("Entre el minuto 5 y 13 presionaron", "es") == [
        (5.0, "minute"),
        (13.0, "minute"),
    ]
    assert _values("Entre os minutos 5 e 13", "pt") == [(5.0, "minute"), (13.0, "minute")]
    assert _values("between minutes 5 and 13", "en") == [(5.0, "minute"), (13.0, "minute")]
    assert _values("from 5' to 13'", "en") == [(5.0, "minute"), (13.0, "minute")]
    assert _values("بين الدقيقة ٥ و١٣", "ar") == [(5.0, "minute"), (13.0, "minute")]
    assert check_text("Entre el minuto 5 y 13.", "es", [], _verified, minutes={5, 13}).ok
    assert _values("minute 5 and 2 shots", "en")[1] == (2.0, None)  # not a range: words between
