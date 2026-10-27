"""A team's number must be given to that team (TASK-25.2, planted error ``e19``).

The number check matches by value: "Atlético Chapinero allow 8.7 passes per defensive
action" passed because 8.7 is a verified claim, though it is Laureles' PPDA. Here each
number that matches only team claims is tied to the team named nearest before it in its
sentence; if that team owns none of the matching claims, the sentence gives the number to
the wrong side. Kept deliberately narrow, so it never fires on correct text:
- only team claims (a player's or the game's numbers aren't checked);
- only when exactly one team is named earlier in the sentence (with two, the subject is
  usually the first: "El Prado exploited Getsemaní's press, controlling 40%"), in the
  same clause, at most ``MAX_GAP`` words before
  the number, with no comma, semicolon, colon, or bracket between them ("Getsemaní,
  controlando el 40,2 %" describes the sentence's subject, not Getsemaní);
- not when a word between them points to the other side or a comparison ("by",
  "against", "their opponents", "vs", "frente a", "مقابل", ...), as in "pinned back by
  72% field tilt";
- PPDA is often told from the passing side ("dejando a El Poblado con 4,7 pases por acción
  defensiva" is San Fernando's PPDA, correctly): not when a verb like "allowing",
  "leaving", "limiting" comes before the team's name;
- not for "the last 10 minutes" (a window, like the number check);
- not after "outshot"/"outscored" ("outshot San Antonio 15 to 6"), and not when a fan
  text says "our"/"nuestro"/"notre" (its own, unnamed club) after the team;
- not when the first team named after the number in its sentence owns it, as in
  "0,01 do Chapinero" or Arabic "٠٫٠١ لـ Chapinero".
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from matchmind.agents.numbers import (
    WINDOWS,
    _candidates,
    _close,
    extract_numbers,
    fold,
)
from matchmind.schemas import Claim, Lang

_TEAM_SCOPE = re.compile(r"/team:(?P<id>[^/]+)$")
MAX_GAP = 8
_CLAUSE_BREAK = re.compile(r"[,;:()،؛]")
_SENTENCE_END = re.compile(r"[.!?؟](?:\s|$)|\n")
# Words that hand a number to the other side, folded (lowercase, no accents).
_OTHER_SIDE: dict[str, str] = {
    "en": r"by|against|rivals?|opponents?|opposition|visitors|hosts|face[sd]?|facing"
          r"|vs\.?|versus|compared|while|whereas|than|our|we|us",
    "es": r"por|contra|rivale?s?|adversarios?|visitantes?|locales|frente|ante|mientras"
          r"|que|comparado|nuestr[oa]s?|nosotros|nos",
    "pt": r"pel[oa]s?|por|contra|adversarios?|rival|rivais|visitantes?|diante|enquanto"
          r"|que|comparado|noss[oa]s?|nos",
    "fr": r"par|contre|adversaires?|rival|rivaux|visiteurs|face|tandis|que|compare|notre"
          r"|nos|nous",
    "ar": r"الخصم|المنافس|ضد|أمام|من قبل|مقابل|بينما|مقارنة|من|\w+نا",
}  # fmt: skip
# Verbs that make the team after them the passing side of a PPDA ("allowing Getsemaní").
_ALLOWING: dict[str, str] = {
    "en": r"allow\w*|leav\w*|left|limit\w*|forc\w*|restrict\w*|held|hold\w*|kept|keep\w*"
          r"|giv\w*|gave",
    "es": r"permit\w*|dej\w*|limit\w*|oblig\w*|forz\w*|da|dio|dando",
    "pt": r"permit\w*|deix\w*|limit\w*|forc\w*|obrig\w*|da|deu|dando",
    "fr": r"permet\w*|laiss\w*|limit\w*|forc\w*|oblig\w*|donn\w*",
    "ar": r"\w*سمح\w*|\w*أجبر\w*|\w*منح\w*|\w*ترك\w*",
}  # fmt: skip
_PPDA = ("ppda", "ppda_10min")
# "outshot San Antonio 15 to 6": the first number is the other side's, for any metric.
_BEATING = re.compile(r"(?<!\w)out(?:shot|shooting|scored?|scoring|pass\w*|play\w*|run)(?!\w)")
_WINDOW = re.compile(r"\s*(?:\w+\s+)?(?:minutes|minutos|min\b|دقائق)", re.IGNORECASE)


def _owners(claims: Sequence[Claim]) -> list[str] | None:
    """The teams owning ``claims``, or None if any isn't a team claim."""
    out = []
    for c in claims:
        m = _TEAM_SCOPE.search(c.ref)
        if m is None:
            return None
        out.append(m["id"])
    return out


def _named_in(prefix: str, teams: Mapping[str, Sequence[str]]) -> list[tuple[str, int, int]]:
    """Every team named in ``prefix`` (folded): (club id, start, end), in order."""
    found = [
        (cid, m.start(), m.end())
        for cid, variants in teams.items()
        for v in variants
        for m in re.finditer(rf"(?<!\w){re.escape(v)}(?!\w)", prefix)
    ]
    return sorted(found, key=lambda f: (f[1], -f[2]))


def _named_first(suffix: str, teams: Mapping[str, Sequence[str]]) -> str | None:
    """The team named first in ``suffix`` (folded)."""
    best: tuple[str, int] | None = None
    for cid, variants in teams.items():
        for v in variants:
            m = re.search(rf"(?<!\w){re.escape(v)}(?!\w)", suffix)
            if m and (best is None or m.start() < best[1]):
                best = (cid, m.start())
    return best[0] if best else None


def owner_failures(
    text: str, lang: Lang, claims: Sequence[Claim], teams: Mapping[str, Sequence[str]]
) -> list[str]:
    """One failure per number that the nearest team named before it doesn't own.
    ``teams`` maps club ids to folded name variants (``scoreline.team_variants``)."""
    failures = []
    # Patterns are matched on folded text, so they're folded too (Arabic "أ" loses its hamza).
    other_side = re.compile(rf"(?<!\w)(?:{fold(_OTHER_SIDE.get(lang, '(?!)'))})(?!\w)")
    allowing = re.compile(rf"(?<!\w)(?:{fold(_ALLOWING.get(lang, '(?!)'))})(?!\w)")
    windows = set(WINDOWS.values())
    for n in extract_numbers(text, lang):
        if n.unit in ("minute", "score", "formation"):
            continue
        if n.decimals == 0 and n.value in windows and _WINDOW.match(text[n.span[1] :]):
            continue
        matching = [
            c for c in claims
            if any(_close(n.value, cand, n.decimals, 0.01, 0.05)
                   for cand in _candidates(c.value, c.unit, n.unit))
        ]  # fmt: skip
        owners = _owners(matching) if matching else None
        if not owners:
            continue
        ends = [m.start() for m in _SENTENCE_END.finditer(text, n.span[1])]
        after = fold(text[n.span[1] : min([*ends, len(text)])])
        named_after = _named_first(after, teams)
        if named_after is not None and named_after in owners:
            continue
        starts = [m.end() for m in _SENTENCE_END.finditer(text, 0, n.span[0])]
        prefix = fold(text[(starts[-1] if starts else 0) : n.span[0]])
        named_all = _named_in(prefix, teams)
        if len({cid for cid, _, _ in named_all}) != 1:
            continue
        cid, start, end = named_all[-1]
        if cid in owners:
            continue
        if any(c.metric in _PPDA for c in matching) and allowing.search(prefix[:start]):
            continue
        if _BEATING.search(prefix[:start]):
            continue
        named = (cid, end)
        between = prefix[end:]
        if (other_side.search(between) or _CLAUSE_BREAK.search(between)
                or len(between.split()) > MAX_GAP):  # fmt: skip
            continue
        owner, given = teams[owners[0]][-1].title(), teams[named[0]][-1].title()
        written = text[n.span[0] : n.span[1]]
        failures.append(
            f"number {written!r} is {owner}'s ({matching[0].metric}), but the sentence gives "
            f"it to {given}"
        )
    return failures
