"""Insights in a persona and language, and the "why" behind one insight."""

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from matchmind.agents.orchestrator import Regenerated
from matchmind.agents.templates import render
from matchmind.api.ratelimit import client_ip
from matchmind.api.services import Json, Svc
from matchmind.schemas import Lang, MatchMeta, Persona, Variant

router = APIRouter(prefix="/api")

Regenerator = Callable[[str, Variant, Lang], Awaitable[Regenerated]]
REGENERATE_TIMEOUT_S = 120.0


def _variant(meta: MatchMeta, persona: Persona, club_id: str | None,
             player_id: str | None) -> Variant:  # fmt: skip
    """The fan a text is for: ``club_fan`` defaults to the home club, ``player_focus``
    needs a player in the match (422 otherwise)."""
    if persona == "club_fan":
        club_id = club_id or meta.home.club_id
        if club_id not in (meta.home.club_id, meta.away.club_id):
            raise HTTPException(422, f"club {club_id!r} is not in {meta.match_id!r}")
    if persona == "player_focus" and player_id not in {
        p.player_id for p in meta.home_squad + meta.away_squad
    }:
        raise HTTPException(422, "player_focus needs the player_id of a player in the match")
    return Variant(
        persona=persona,
        club_id=club_id if persona == "club_fan" else None,
        player_id=player_id if persona == "player_focus" else None,
    )


@router.get("/matches/{match_id}/insights")
def insights(
    match_id: str,
    svc: Svc,
    persona: Persona,
    lang: Lang,
    club_id: str | None = None,
    player_id: str | None = None,
) -> list[Json]:
    """Every verified insight in time order, with its text for (persona, lang). A
    ``club_fan`` text is for ``club_id`` (default: the home club); ``player_focus`` needs
    ``player_id``. A variant the precompute did not write gets its template."""
    meta = svc.meta(match_id)
    variant = _variant(meta, persona, club_id, player_id)
    stored = {
        (t.insight_id, t.club_id, t.player_id): t
        for t in svc.repo.list_personalized(match_id, persona=persona, lang=lang)
    }
    order = {m.moment_id: (m.period, m.t_start) for m in svc.repo.list_moments(match_id)}
    found = [i for i in svc.repo.list_insights(match_id) if i.verified]
    found.sort(key=lambda i: order.get(i.moment_id, (3, 0.0)))
    names = svc.names(meta)
    rows = []
    for ins in found:
        text = stored.get((ins.insight_id, variant.club_id, variant.player_id))
        if text is None:
            text = render(ins, variant, lang, names)
        rows.append({"insight": ins.model_dump(), "text": text.model_dump()})
    return rows


@router.get("/insights/{insight_id}/why")
def why(insight_id: str, svc: Svc) -> Json:
    """The evidence: claims, cited events, agent runs, trace id, and the counterfactual of
    the first cited decision (pass, carry, shot, or clearance), if any."""
    ins = svc.repo.get_insight(insight_id)
    if ins is None:
        raise HTTPException(404, f"unknown insight {insight_id!r}")
    events = [e for eid in ins.event_ids if (e := svc.repo.get_event(eid)) is not None]
    decision = next((e for e in events if "best_score" in e.extras), None)
    counterfactual = None
    if decision is not None:
        cf = svc.stats.get_counterfactual(decision.event_id)
        counterfactual = None if "error" in cf else cf
    return {
        "claims": [c.model_dump() for c in ins.claims],
        "events": [e.model_dump() for e in events],
        "agent_runs": [r.model_dump() for r in svc.repo.list_agent_runs(ins.moment_id)],
        "trace_id": ins.trace_id,
        "counterfactual": counterfactual,
    }


class RegenerateBody(BaseModel):
    moment_id: str
    persona: Persona
    lang: Lang
    club_id: str | None = None
    player_id: str | None = None


@router.post("/matches/{match_id}/regenerate", response_model=None)
async def regenerate(
    match_id: str, body: RegenerateBody, request: Request, svc: Svc
) -> Json | JSONResponse:
    """Run the agents live on one moment for one fan (nothing is saved). Rate limited:
    5 an hour per visitor and 100 a day in all; over a limit, 429 with ``retry_after``.
    Invalid requests (422, 404) are not counted."""
    meta = svc.meta(match_id)
    moment = svc.repo.get_moment(body.moment_id)
    if moment is None or moment.match_id != match_id:
        raise HTTPException(404, f"unknown moment {body.moment_id!r} in {match_id!r}")
    variant = _variant(meta, body.persona, body.club_id, body.player_id)
    wait = request.app.state.limiter.hit(client_ip(request))
    if wait is not None:
        return JSONResponse(
            {"detail": "too many live runs; try again later", "retry_after": wait},
            status_code=429, headers={"Retry-After": str(wait)},
        )  # fmt: skip
    regenerator: Regenerator = request.app.state.regenerator
    try:
        out = await asyncio.wait_for(
            regenerator(body.moment_id, variant, body.lang), REGENERATE_TIMEOUT_S
        )
    except TimeoutError:
        raise HTTPException(504, "the agents took too long") from None
    return {
        "insight": out.insight.model_dump(),
        "text": out.text.model_dump(),
        "agent_runs": [r.model_dump() for r in out.runs],
        "trace_id": out.insight.trace_id,
    }
