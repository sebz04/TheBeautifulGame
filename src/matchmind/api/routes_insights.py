"""Insights in a persona and language, and the "why" behind one insight."""

from fastapi import APIRouter, HTTPException

from matchmind.agents.templates import render
from matchmind.api.services import Json, Svc
from matchmind.schemas import Lang, Persona, Variant

router = APIRouter(prefix="/api")


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
    if persona == "club_fan":
        club_id = club_id or meta.home.club_id
        if club_id not in (meta.home.club_id, meta.away.club_id):
            raise HTTPException(422, f"club {club_id!r} is not in {match_id!r}")
    if persona == "player_focus" and player_id not in {
        p.player_id for p in meta.home_squad + meta.away_squad
    }:
        raise HTTPException(422, "player_focus needs the player_id of a player in the match")
    variant = Variant(
        persona=persona,
        club_id=club_id if persona == "club_fan" else None,
        player_id=player_id if persona == "player_focus" else None,
    )
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
