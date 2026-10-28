"""Interpretation slips (TASK-25.2, ``docs/evals.md``): PPDA read as pressure faced, and
recap sentences that mix stats from different moments.

PPDA is how many passes the opponent makes for each defensive action by this team: it
measures this team's own pressing. Agents kept writing "Laureles faced less pressure with a
PPDA of 24.3", reading it as the pressure a team faces, even with the Terms section in the
prompts; the events don't contradict it, so the Verifier agent let it through. Here a
sentence fails when it mentions PPDA and says a side faces or suffers pressure without
naming who applies it. "Under pressure" and "pressure from X" / "presión de X" / "pression
d'X" are left alone: those describe the other side's press, which is a correct reading.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from matchmind.agents.numbers import _candidates, _close, extract_numbers, fold
from matchmind.clock import minute_label
from matchmind.schemas import Claim, Lang

_PPDA = re.compile(
    r"ppda|per defensive action|por accion defensiva|por acao defensiva|par action defensive"
)
# "Faces less pressure": a verb of facing or suffering, then (within a few words) pressure,
# not followed by who applies it. Matched on folded text (lowercase, no accents).
_FACING: dict[str, str] = {
    "en": r"\bfac(?:e|es|ed|ing)\b(?:\s+\w+){0,3}\s+pressure\b(?!\s+(?:from|by|of)\b)",
    "es": r"\b(?:enfrent|sufr)\w*(?:\s+\w+){0,3}\s+presion\b(?!\s+(?:de|del)\b)",
    "pt": r"\b(?:enfrent|sofr)\w*(?:\s+\w+){0,3}\s+pressao\b(?!\s+(?:de|do|da|dos|das)\b)",
    "fr": r"\b(?:subi|subiss|subit|subissent|fai\w*\s+face\s+a)\w*(?:\s+[\w']+){0,3}\s*"
          r"pression\b(?!\s+(?:de|du|des|d')|\s*d')",
}  # fmt: skip
_SENTENCES = re.compile(r"(?<=[.!?؟])\s+|\n")


def ppda_slips(text: str, lang: Lang) -> list[str]:
    """One failure per sentence that reads PPDA as the pressure a team faces."""
    facing = _FACING.get(lang)
    if facing is None:
        return []
    pattern = re.compile(facing)
    failures = []
    for sentence in _SENTENCES.split(text):
        folded = fold(sentence)
        if _PPDA.search(folded) and (hit := pattern.search(folded)):
            failures.append(
                f"'{sentence[hit.start() : hit.end()]}' reads PPDA as the pressure a team faces; "
                "PPDA measures a team's own pressing (passes the opponent makes per defensive "
                "action by that team: lower means it presses harder). Say who presses, or "
                "write 'under pressure from' the pressing side"
            )
    return failures


_AT = re.compile(r"@(?P<period>[12]):(?P<t>[\d.]+)/")


def mixed_moments(text: str, lang: Lang, claims: Sequence[Claim]) -> list[str]:
    """One failure per sentence whose numbers come only from claims of two or more different
    moments (the ``@period:t`` of their refs): seen live in a recap that put a 20' press and
    a 60' momentum in one sentence, as if at the same time."""
    failures = []
    for sentence in _SENTENCES.split(text):
        moments: set[tuple[Literal[1, 2], float]] = set()
        numbers = extract_numbers(sentence, lang)
        if sum(n.unit == "minute" for n in numbers) >= 2:
            continue  # it says when each was
        for n in numbers:
            if n.unit in ("minute", "score", "formation"):
                continue
            at: set[tuple[Literal[1, 2], float]] = {
                (1 if m["period"] == "1" else 2, float(m["t"]))
                for c in claims
                if (m := _AT.search(c.ref))
                and any(_close(n.value, cand, n.decimals, 0.01, 0.05)
                        for cand in _candidates(c.value, c.unit, n.unit))
            }  # fmt: skip
            if len(at) == 1:  # a number that fits claims at several moments says nothing
                moments |= at
        if len(moments) > 1:
            when = " and ".join(minute_label(p, t) for p, t in sorted(moments))
            failures.append(
                f"'{sentence.strip()[:80]}' quotes stats from different moments ({when}) as if "
                "at the same time: one moment per sentence, or say when each was"
            )
    return failures
