"""Lead wording must match the score at the moment (TASK-24.4).

The Verifier checks numbers, not who is winning, so "Morejo gives Chapinero the lead" passed
at 1–1. This check finds phrases that tie a lead to a named team ("puts Laureles ahead",
"da ventaja a Laureles", "prend l'avantage", ...) and fails them when that team isn't
strictly ahead at the moment's end. Other meanings ("leads the press", "numerical
advantage") are deliberately not matched: only score phrasing next to a team name.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from matchmind.agents.numbers import fold

GENERIC = {"atletico", "club", "deportivo", "sporting", "union", "futbol", "fc", "cd",
           "de", "del", "la", "el", "los", "las", "san"}  # fmt: skip

# {T} is a team name. Patterns are matched on folded text (lowercase, no accents).
_LEAD: dict[str, list[str]] = {
    "en": [
        r"\bgives? (?:the )?{T} the lead\b",
        r"\bputs? (?:the )?{T} (?:ahead|in front)\b",
        r"\b{T} (?:go|goes|went|are|is|move|moves|moved|get|gets|got)"
        r" (?:back )?(?:ahead|in front)\b",
        r"\b{T} (?:take|takes|took|retake|retakes|regain|regains) the lead\b",
        r"\b{T}(?:'s|’s)? lead (?:of|by) \d",
    ],
    "es": [
        r"\b(?:da|dan|dio|pone|ponen|puso|devuelve) (?:la )?ventaja (?:a|al) (?:nuestro )?{T}",
        r"\b{T} (?:se pone|se puso|queda|va|pasa) (?:por )?delante\b",
        r"\b{T} se adelanta\b",
        r"\badelanta (?:a|al) {T}",
        r"\bpone (?:por )?delante (?:a|al) {T}",
        r"\b{T} toma la (?:delantera|ventaja)\b",
    ],
    "pt": [
        r"\b(?:garante|da|deu|coloca|colocou|poe|pos) (?:a )?vantagem"
        r" (?:para|ao|a|pro) (?:o |nosso )?{T}",
        r"\b(?:coloca|colocou|poe|pos) (?:o )?{T} (?:a|na) frente\b",
        r"\b{T} (?:passa|passou|fica|ficou|vai|sai|saiu) (?:a|na) frente\b",
        r"\b{T} (?:assume|assumiu) a lideranca do placar\b",
    ],
    "fr": [
        r"\b{T} (?:prend|prennent|reprend|reprennent) l'avantage\b",
        r"\b(?:donne|offre|redonne) l'avantage (?:a|au|aux) {T}",
        r"\b{T} (?:passe|passent|repasse|est|sont) (?:en tete|devant au score)\b",
        r"\b(?:met|place|remet) {T} (?:en tete|devant)\b",
    ],
    "ar": [
        r"يمنح {T} التقدم",
        r"(?:^|\s){T} يتقدم(?:\s|$)",
        r"تقدم {T}",
    ],
}


def team_variants(names: Mapping[str, str]) -> dict[str, list[str]]:
    """Ways a text names each club: its full name and each word no other club shares
    (folded), longest first so "atletico chapinero" wins over "chapinero"."""
    folded = {cid: fold(name) for cid, name in names.items()}
    words = {
        cid: [w for w in re.split(r"[\s\-]+", f) if w and w not in GENERIC]
        for cid, f in folded.items()
    }
    out: dict[str, list[str]] = {}
    for cid, f in folded.items():
        others = {w for o, ws in words.items() if o != cid for w in ws}
        own = [w for w in words[cid] if w not in others]
        tail = " ".join(words[cid]) if len(words[cid]) > 1 else None
        variants = [f, *([tail] if tail else []), *own]
        out[cid] = sorted(dict.fromkeys(variants), key=len, reverse=True)
    return out


def _team_alternation(variants: Sequence[str]) -> str:
    return "(?:" + "|".join(re.escape(v) for v in variants) + ")"


def lead_failures(text: str, lang: str, teams: Mapping[str, Sequence[str]],
                  score: Mapping[str, int]) -> list[str]:  # fmt: skip
    """One failure per sentence that says a team is ahead when, by ``score`` (goals by
    club id at the moment's end), it isn't."""
    folded = fold(text)
    failures = []
    for cid, variants in teams.items():
        others = [g for c, g in score.items() if c != cid]
        ahead = score.get(cid, 0) > max(others, default=0)
        if ahead:
            continue
        name = _team_alternation(variants)
        for pattern in _LEAD.get(lang, []):
            hit = re.search(pattern.replace("{T}", name), folded)
            if hit:
                line = "–".join(str(score[c]) for c in score)
                failures.append(
                    f"says {variants[-1].title()} lead(s) ('{text[hit.start() : hit.end()]}'), "
                    f"but the score at this moment is {line}"
                )
                break
    return failures
