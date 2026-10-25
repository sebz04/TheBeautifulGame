"""Locale-aware number extraction and checking for agent text (the Verifier's hard rule).

Every number an agent writes must match a verified stat, a real event minute, or the
real score. Numbers are read the way each language writes them: decimal commas
(es, pt, fr), thousands separators (``12.000``, ``12 000``, ``12,000``), Arabic-Indic
digits, and number words 0-20. A number that cannot be matched is a failure; nothing
is silently skipped.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Collection, Iterator, Sequence
from dataclasses import dataclass, field

from matchmind.schemas import Claim, Lang

_DIGITS = "0-9٠-٩۰-۹"
_RUN = re.compile(f"[{_DIGITS}]+")
_TO_ASCII = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_SPACES = {" ", " ", " "}
_GROUP: dict[str, set[str]] = {
    "en": {","},
    "ar": {",", "٬"},
    "es": {"."} | _SPACES,
    "pt": {"."} | _SPACES,
    "fr": {"."} | _SPACES,
}
_DECIMAL: dict[str, set[str]] = {
    "en": {"."},
    "ar": {".", "٫"},
    "es": {","},
    "pt": {","},
    "fr": {","},
}
# A separator that is not a 3-digit group is read as a decimal point, in any language:
# "1.5" in a Spanish sentence means 1.5, not an error.
_FALLBACK_DECIMAL = {".", ","}

_UNITS = re.compile(
    r"\s*(?:"
    r"(?P<pct>%|٪|por\s?ciento|pour\s?cent|per\s?cent|percent|por\s?cento)"
    r"|(?P<kmh>km/h|km/hr|kph|كم/س(?:اعة)?)"
    r"|(?P<ms>m/s)"
    r"|(?P<km>km|kil[oó]m[eè]tr[eo]s?|kilometers?|quil[oô]metros?|كم|كيلومترات?)(?![^\W\d_])"
    r"|(?P<m>m|metros?|meters?|metres?|mètres?|مترا?|أمتار)(?![^\W\d_])"
    r")",
    re.IGNORECASE,
)
_UNIT_NAME = {"pct": "%", "kmh": "km/h", "ms": "m/s", "km": "km", "m": "m"}

_MINUTE_WORDS = r"min\b\.?|minutes?\b|minutos?\b|minuto\b|دقيقة|الدقيقة"
_MINUTE_AFTER = re.compile(
    rf"(?:st|nd|rd|th|ème|eme|er|e|º|ª|°)?\s*(?:['’′]|{_MINUTE_WORDS})", re.IGNORECASE
)
_MINUTE_BEFORE = re.compile(r"(?:minute|minuto|min\.?|الدقيقة|دقيقة)\s*(?:de\s+)?$", re.I)
_STOPPAGE = re.compile(r"\s*\+\s*$")
_FORMATION = re.compile(r"[1-6](?:[-–][1-6]){2,3}(?![-–]?\d)")
_SCORE_GAP = re.compile(r"^\s*[-–—:]\s*$|^\s+(?:a|à|مقابل)\s+$", re.IGNORECASE)


def _zero_to_twenty(words: str) -> dict[str, int]:
    """Map the 20 space-separated words for 0 and 2..20 to their values."""
    return dict(zip(words.split(), [0, *range(2, 21)], strict=True))


# Number words 0-20, accent-folded. Words for 1 are left out on purpose: un, una, um,
# une, one double as articles and pronouns, so reading them as numbers would flag
# almost every sentence.
_WORDS: dict[str, dict[str, int]] = {
    "en": _zero_to_twenty(
        "zero two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen twenty"
    ),
    "es": _zero_to_twenty(
        "cero dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce "
        "quince dieciseis diecisiete dieciocho diecinueve veinte"
    ),
    "pt": {
        "zero": 0, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
        "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13,
        "catorze": 14, "quatorze": 14, "quinze": 15, "dezesseis": 16, "dezasseis": 16,
        "dezessete": 17, "dezassete": 17, "dezoito": 18, "dezenove": 19, "dezanove": 19,
        "vinte": 20,
    },
    "fr": _zero_to_twenty(
        "zero deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze "
        "quinze seize dix-sept dix-huit dix-neuf vingt"
    ),
    "ar": {
        "صفر": 0, "اثنان": 2, "اثنين": 2, "اثنتان": 2, "اثنتين": 2, "ثلاثة": 3, "ثلاث": 3,
        "اربعة": 4, "اربع": 4, "خمسة": 5, "خمس": 5, "ستة": 6, "ست": 6, "سبعة": 7, "سبع": 7,
        "ثمانية": 8, "ثماني": 8, "ثمان": 8, "تسعة": 9, "تسع": 9, "عشرة": 10, "عشر": 10,
        "عشرون": 20, "عشرين": 20,
    },
}  # fmt: skip
# Arabic teens are two words: a unit then عشر / عشرة ("ثلاثة عشر" = 13).
_AR_TEEN_UNITS = {"احد": 1, "احدى": 1, "اثنا": 2, "اثنتا": 2, "اثني": 2, "اثنتي": 2}
_AR_TEN = {"عشر", "عشرة"}
_AR_PREFIXES = ("وال", "بال", "ال", "لل", "و", "ب", "ل")
_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")


@dataclass(frozen=True)
class ExtractedNumber:
    """A number as written: its value, where it is, and what kind of number it is.

    ``unit`` is one of ``None``, ``"%"``, ``"km/h"``, ``"m/s"``, ``"km"``, ``"m"``,
    ``"minute"``, ``"score"`` (then ``pair`` holds both sides) or ``"formation"``
    (then ``formation`` holds it, such as ``"4-2-3-1"``).
    """

    value: float
    span: tuple[int, int]
    unit: str | None = None
    decimals: int = 0
    pair: tuple[int, int] | None = None
    formation: str | None = None


@dataclass(frozen=True)
class NumberCheck:
    ok: bool
    failures: list[str] = field(default_factory=list)


def fold(word: str) -> str:
    decomposed = unicodedata.normalize("NFD", word.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _digit_numbers(text: str, lang: str) -> Iterator[ExtractedNumber]:
    runs = list(_RUN.finditer(text))
    i = 0
    while i < len(runs):
        start, end = runs[i].span()
        whole, frac = runs[i].group(), ""
        j = i + 1
        while j < len(runs):
            gap, nxt = text[end : runs[j].start()], runs[j].group()
            if len(gap) != 1:
                break
            if gap in _DECIMAL[lang] or (gap not in _GROUP[lang] and gap in _FALLBACK_DECIMAL):
                frac = nxt
            elif gap in _GROUP[lang] and len(nxt) == 3:
                whole += nxt
            elif gap in _FALLBACK_DECIMAL:
                frac = nxt
            else:
                break
            end = runs[j].end()
            j += 1
            if frac:
                break
        value = float(f"{whole}.{frac or 0}".translate(_TO_ASCII))
        yield ExtractedNumber(value, (start, end), decimals=len(frac))
        i = j


def _word_numbers(text: str, lang: str) -> Iterator[ExtractedNumber]:
    words = _WORDS[lang]
    tokens = list(_WORD.finditer(text))
    skip = False
    for k, tok in enumerate(tokens):
        if skip:
            skip = False
            continue
        folded = fold(tok.group())
        if lang == "ar":
            nxt = fold(tokens[k + 1].group()) if k + 1 < len(tokens) else ""
            unit = _ar_word(folded, {**words, **_AR_TEEN_UNITS})
            if unit is not None and 1 <= unit <= 9 and nxt in _AR_TEN:
                skip = True
                yield ExtractedNumber(float(10 + unit), (tok.start(), tokens[k + 1].end()))
                continue
            value = _ar_word(folded, words)
        else:
            value = words.get(folded)
        if value is not None:
            yield ExtractedNumber(float(value), tok.span())


def _ar_word(folded: str, words: dict[str, int]) -> int | None:
    if folded in words:
        return words[folded]
    for prefix in _AR_PREFIXES:
        if folded.startswith(prefix) and folded[len(prefix) :] in words:
            return words[folded[len(prefix) :]]
    return None


def extract_numbers(text: str, lang: Lang) -> list[ExtractedNumber]:
    """Every number in ``text``, read the way ``lang`` writes numbers, in text order."""
    shapes = [m for m in _FORMATION.finditer(text.translate(_TO_ASCII))]
    taken = [m.span() for m in shapes]
    out = [
        ExtractedNumber(0.0, m.span(), "formation", formation=m.group().replace("–", "-"))
        for m in shapes
    ]
    raw = sorted(
        (
            n
            for n in [*_digit_numbers(text, lang), *_word_numbers(text, lang)]
            if not any(a <= n.span[0] < b for a, b in taken)
        ),
        key=lambda n: n.span,
    )
    i = 0
    while i < len(raw):
        n = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else None
        between = text[n.span[1] : nxt.span[0]] if nxt else ""
        whole = n.decimals == 0 and (nxt is None or nxt.decimals == 0)
        if nxt and whole and _STOPPAGE.match(between):  # 90+3'
            out.append(ExtractedNumber(n.value + nxt.value, (n.span[0], nxt.span[1]), "minute"))
            i += 2
            continue
        if nxt and whole and _SCORE_GAP.match(between):
            pair = (int(n.value), int(nxt.value))
            out.append(ExtractedNumber(0.0, (n.span[0], nxt.span[1]), "score", pair=pair))
            i += 2
            continue
        out.append(_with_unit(text, n))
        i += 1
    return sorted(out, key=lambda n: n.span)


def _with_unit(text: str, n: ExtractedNumber) -> ExtractedNumber:
    after, before = text[n.span[1] :], text[max(0, n.span[0] - 20) : n.span[0]]
    if n.decimals == 0 and (_MINUTE_AFTER.match(after) or _MINUTE_BEFORE.search(before)):
        return ExtractedNumber(n.value, n.span, "minute")
    unit = _UNITS.match(after)
    if unit and unit.lastgroup:
        return ExtractedNumber(n.value, n.span, _UNIT_NAME[unit.lastgroup], n.decimals)
    return n


WINDOWS = {"_10min": 10.0, "momentum": 5.0}  # metric suffix -> window length in minutes
_PLURAL_MINUTES = re.compile(r"\s*(?:minutes|minutos|mins\b|دقائق)", re.IGNORECASE)
_CLAIM_UNITS = {
    "%": "%", "percent": "%", "pct": "%",
    "km/h": "km/h", "kmh": "km/h", "m/s": "m/s",
    "km": "km", "m": "m", "meters": "m", "metres": "m",
}  # fmt: skip
_CONVERT = {("km/h", "m/s"): 3.6, ("m/s", "km/h"): 1 / 3.6, ("m", "km"): 1000.0, ("km", "m"): 1e-3}


def _candidates(verified: float, claim_unit: str, written_unit: str | None) -> list[float]:
    """Values a writer could correctly print for ``verified`` given the written unit."""
    cu = _CLAIM_UNITS.get(claim_unit.strip().lower())
    if written_unit in (None, "%") and cu in (None, "%"):
        return [verified, verified * 100] if "%" in (written_unit, cu) else [verified]
    if cu is None or cu == written_unit or written_unit is None:
        return [verified]
    factor = _CONVERT.get((written_unit, cu))
    return [verified * factor] if factor else []


def _close(x: float, target: float, decimals: int, rel_tol: float, abs_tol: float) -> bool:
    """Within tolerance, or equal to ``target`` rounded to the precision ``x`` is written in."""
    diff = abs(x - target)
    return diff <= max(abs_tol, rel_tol * abs(target)) or diff <= 0.5 * 10**-decimals + 1e-9


def _decimals(value: float) -> int:
    """Decimal places a claim value was given to (0.62 -> 2, 41.0 -> 0)."""
    text = repr(float(value))
    return 9 if "e" in text else len(text.split(".")[1].rstrip("0"))


def check_text(
    text: str,
    lang: Lang,
    claims: Sequence[Claim],
    lookup: Callable[[Claim], float | None],
    rel_tol: float = 0.01,
    abs_tol: float = 0.05,
    *,
    minutes: Collection[int] = (),
    scores: Collection[tuple[int, int]] = (),
    formations: Collection[str] = (),
) -> NumberCheck:
    """Check every number in ``text`` against the claims' verified values.

    ``lookup`` returns the stored value behind a claim (None if its ref is unknown).
    Each claim must agree with its stored value; each number in the text must match a
    verified claim (allowing unit conversion and rounding to the written precision),
    a real event minute (``minutes``), a real scoreline (``scores``, either order), or a
    formation a team actually used (``formations``, such as ``"4-4-2"``).
    """
    failures: list[str] = []
    verified: list[tuple[float, str]] = []
    for c in claims:
        stored = lookup(c)
        if stored is None:
            failures.append(
                f"unverifiable claim {c.text!r} ({c.metric}, ref {c.ref}): no stored value"
            )
        elif not any(
            _close(c.value, target, _decimals(c.value), rel_tol, 0.0)
            for target in _candidates(stored, c.unit, None)
        ):
            failures.append(
                f"claim {c.text!r} says {c.metric}={c.value:g}, but the stats say {stored:g} "
                f"(ref {c.ref})"
            )
        else:
            verified.append((stored, c.unit))
    # "over the last 10 minutes" describes a cited window metric's window, not a stat.
    windows = {w for suffix, w in WINDOWS.items() if any(c.metric.endswith(suffix) for c in claims)}
    verified += [(w, "") for w in windows]

    for n in extract_numbers(text, lang):
        written = text[n.span[0] : n.span[1]]
        if n.unit == "minute":
            window = n.value in windows and _PLURAL_MINUTES.match(text[n.span[1] :])
            if round(n.value) not in minutes and not window:
                failures.append(f"minute {written!r} matches no event minute")
        elif n.unit == "formation":
            if n.formation not in formations:
                failures.append(f"formation {written!r} was not used in this match")
        elif n.unit == "score":
            assert n.pair is not None
            if n.pair not in scores and n.pair[::-1] not in scores:
                failures.append(f"scoreline {written!r} is not the match score")
        elif not any(
            _close(n.value, cand, n.decimals, rel_tol, abs_tol)
            for value, unit in verified
            for cand in _candidates(value, unit, n.unit)
        ):
            context = " ".join(text[max(0, n.span[0] - 25) : n.span[1] + 25].split())
            failures.append(f"number {written!r} (in “…{context}…”) matches no verified stat")
    return NumberCheck(ok=not failures, failures=failures)
