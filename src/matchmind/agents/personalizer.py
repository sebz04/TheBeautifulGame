"""Personalization: one verified insight rewritten for each fan, in one language per call.

``personalize_batch`` asks for every variant of an insight in one model call per language,
to save tokens and quota. Code then checks each variant: numbers (only the insight's claims,
in the language's own format), word limit, no jargon for casual fans, and the club or
player it is for named in the text. Variants that fail are asked for once more, alone;
whatever still fails gets its deterministic template, so one bad variant never sinks the
rest. Agent texts come back ``verified=False``: the Verifier checks their wording in their
own language in the workflow (TASK-20, Constitution II). Templates are already verified.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from agent_framework.exceptions import ChatClientException
from pydantic import BaseModel

from matchmind.agents.numbers import check_text, fold
from matchmind.agents.runtime import bad_reply, make_agent, run_agent
from matchmind.agents.templates import WORD_LIMITS, jargon_in, render, word_count
from matchmind.schemas import Insight, Lang, MatchMeta, Persona, PersonalizedText, Variant

log = logging.getLogger(__name__)
PROMPT = "personalizer.v1.md"
OPTIONS = {"temperature": 0.0}
# Words that don't identify a club on their own ("Atlético", "Club", "Deportivo"...).
GENERIC = {"atletico", "club", "deportivo", "sporting", "union", "futbol", "fc", "cd",
           "de", "del", "la", "el", "los", "las"}  # fmt: skip
_PLAYER = re.compile(r"/player:(?P<id>.+)$")

Key = tuple[str, str | None, str | None]


class TextReply(BaseModel):
    persona: Persona
    club_id: str | None
    player_id: str | None
    headline: str
    body: str


class BatchReply(BaseModel):
    texts: list[TextReply]


def _key(v: Variant | TextReply) -> Key:
    return (v.persona, v.club_id, v.player_id)


def _label(k: Key) -> str:
    return ":".join(x for x in k if x)


def variants_for(insight: Insight, meta: MatchMeta) -> list[Variant]:
    """``analyst``, ``casual``, ``club_fan`` for both clubs, and ``player_focus`` for every
    match player the insight's claims are about (other favorites get the template)."""
    in_match = {p.player_id for p in [*meta.home_squad, *meta.away_squad]}
    players = [m["id"] for c in insight.claims if (m := _PLAYER.search(c.ref))]
    return [
        Variant(persona="analyst"),
        Variant(persona="casual"),
        Variant(persona="club_fan", club_id=meta.home.club_id),
        Variant(persona="club_fan", club_id=meta.away.club_id),
        *(Variant(persona="player_focus", player_id=p) for p in dict.fromkeys(players)
          if p in in_match),
    ]  # fmt: skip


def _mentions(text: str, name: str, *, club: bool) -> bool:
    words = [w for w in fold(name).replace("-", " ").split() if len(w) > 2]
    if club:
        words = [w for w in words if w not in GENERIC] or words
    folded = fold(text)
    return any(re.search(rf"\b{re.escape(w)}\b", folded) for w in words)


def _problems(
    v: Variant, t: TextReply, lang: Lang, insight: Insight, names: Mapping[str, str],
    minutes: Collection[int], scores: Collection[tuple[int, int]],
) -> list[str]:  # fmt: skip
    text = f"{t.headline}\n{t.body}"
    problems = []
    if not t.headline.strip() or not t.body.strip():
        problems.append("the headline or body is empty")
    words, limit = word_count(f"{t.headline} {t.body}"), WORD_LIMITS[v.persona]
    if words > limit:
        problems.append(f"it has {words} words; at most {limit}")
    if v.persona == "casual" and (terms := jargon_in(text)):
        problems.append(f"it uses jargon ({', '.join(terms)}): say it in plain words")
    if v.club_id and not _mentions(text, names.get(v.club_id, v.club_id), club=True):
        problems.append(f"it must name {names.get(v.club_id, v.club_id)}")
    if v.player_id and not _mentions(text, names.get(v.player_id, v.player_id), club=False):
        problems.append(f"it must name {names.get(v.player_id, v.player_id)}")
    check = check_text(text, lang, insight.claims, lambda c: c.value, minutes=minutes,
                       scores=scores)  # fmt: skip
    return problems + check.failures


def _variant_view(v: Variant, names: Mapping[str, str]) -> dict[str, Any]:
    view: dict[str, Any] = {"persona": v.persona}
    if v.club_id:
        view |= {"club_id": v.club_id, "club": names.get(v.club_id, v.club_id)}
    if v.player_id:
        view |= {"player_id": v.player_id, "player": names.get(v.player_id, v.player_id)}
    return view | {"max_words": WORD_LIMITS[v.persona]}


def _message(
    insight: Insight, lang: Lang, pending: Sequence[Variant], names: Mapping[str, str],
    rejected: Mapping[Key, list[str]],
) -> str:  # fmt: skip
    payload: dict[str, Any] = {
        "lang": lang,
        "insight": {k: getattr(insight, k) for k in ("level", "headline", "why", "recommendation")},
        "claims": [c.model_dump() for c in insight.claims],
        "variants": [_variant_view(v, names) for v in pending],
    }
    if rejected:
        payload["rejected"] = {_label(k): p for k, p in rejected.items()}
    header = (
        f"Write these {len(pending)} texts in {lang}."
        if not rejected
        else f"Your texts for {', '.join(_label(k) for k in rejected)} were rejected "
        f"(see `rejected`); write only those again, in {lang}."
    )
    return f"{header}\n{json.dumps(payload, ensure_ascii=False)}"


async def personalize_batch(
    insight: Insight,
    lang: Lang,
    variants: Sequence[Variant],
    client: Any,
    *,
    names: Mapping[str, str],
    minutes: Collection[int] = (),
    scores: Collection[tuple[int, int]] = (),
) -> list[PersonalizedText]:
    """Every variant of ``insight`` in ``lang``: one model call, one retry for the variants
    that fail their checks, then templates. Returned in the order of ``variants``."""
    agent = make_agent("personalizer", PROMPT, BatchReply, None, client=client, options=OPTIONS)
    done: dict[Key, PersonalizedText] = {}
    pending = list(variants)
    rejected: dict[Key, list[str]] = {}
    for attempt in (1, 2):
        message = _message(insight, lang, pending, names, rejected)
        try:
            response = await run_agent(agent, message, moment_id=insight.moment_id, attempt=attempt)
            reply = response.value
        except ChatClientException as exc:
            if bad_reply(exc) is None:
                raise
            reply = None
        got = {_key(t): t for t in reply.texts} if isinstance(reply, BatchReply) else {}
        rejected = {}
        for v in pending:
            t = got.get(_key(v))
            if t is None:
                rejected[_key(v)] = ["it was missing from your answer"]
                continue
            problems = _problems(v, t, lang, insight, names, minutes, scores)
            if problems:
                rejected[_key(v)] = problems
                continue
            done[_key(v)] = PersonalizedText(
                insight_id=insight.insight_id, persona=v.persona, lang=lang,
                headline=t.headline.strip(), body=t.body.strip(), verified=False,
                club_id=v.club_id, player_id=v.player_id, dir="rtl" if lang == "ar" else "ltr",
            )  # fmt: skip
        pending = [v for v in pending if _key(v) in rejected]
        if not pending:
            break
    for v in pending:
        log.warning("template for %s %s %s: %s", insight.insight_id, lang, _label(_key(v)),
                    "; ".join(rejected[_key(v)]))  # fmt: skip
        done[_key(v)] = render(insight, v, lang, names)
    return [done[_key(v)] for v in variants]
