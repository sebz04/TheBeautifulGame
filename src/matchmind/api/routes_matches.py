"""Matches, tracking, timeline, stats, pitch control, recap, and the league."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from matchmind.api.services import Json, Svc, app_version, league
from matchmind.engine.pitch import attacks_right
from matchmind.schemas import Lang, Persona, Recap
from matchmind.stats.deviations import expected_so_far
from matchmind.stats.pitch_control import pitch_control_grid

router = APIRouter(prefix="/api")

MAX_TRACKING_S = 60.0
FRAME_LOOKBACK_S = 0.5  # pitch control uses the last frame at or before t, within this
Period = Annotated[int, Query(ge=1, le=2)]  # Literal[1, 2] rejects the query string "1"
Time = Annotated[float, Query(ge=0)]


@router.get("/health")
def health() -> Json:
    return {"ok": True, "version": app_version()}


@router.get("/matches")
def matches(svc: Svc) -> list[Json]:
    rows = []
    for match_id in svc.repo.list_matches():
        meta = svc.meta(match_id)
        rows.append({
            "match_id": match_id, "title": f"{meta.home.name} v {meta.away.name}",
            "home": meta.home.model_dump(), "away": meta.away.model_dump(),
            "score": svc.score(meta), "scenario_id": meta.scenario_id,
        })  # fmt: skip
    return rows


@router.get("/matches/{match_id}")
def match(match_id: str, svc: Svc) -> Json:
    meta = svc.meta(match_id)
    return meta.model_dump() | {
        "score": svc.score(meta),
        "realism": svc.realism(meta).model_dump(),
    }


@router.get("/matches/{match_id}/tracking")
def tracking(
    match_id: str,
    svc: Svc,
    period: Period,
    t_from: Annotated[float, Query(alias="from", ge=0)],
    t_to: Annotated[float, Query(alias="to", ge=0)],
) -> Json:
    if not 0 <= t_to - t_from <= MAX_TRACKING_S:
        raise HTTPException(422, f"from..to must be 0 to {MAX_TRACKING_S:.0f} s")
    svc.meta(match_id)
    frames = svc.store.read_window(match_id, period, t_from, t_to)
    return {"frames": [f.model_dump() for f in frames]}


@router.get("/matches/{match_id}/timeline")
def timeline(match_id: str, svc: Svc) -> Json:
    meta = svc.meta(match_id)
    moments = sorted(svc.repo.list_moments(match_id), key=lambda m: (m.period, m.t_start))
    momentum = [p.model_dump() for p in svc.momentum(meta).points]
    return {"moments": [m.model_dump() for m in moments], "momentum": momentum}


@router.get("/matches/{match_id}/stats")
def stats(
    match_id: str,
    svc: Svc,
    scope: Literal["team", "player"],
    scope_id: str,
    period: Period,
    t: Time,
) -> Json:
    """Metrics at (period, t), the season expectation so far (players), and the profile."""
    meta = svc.meta(match_id)
    clubs = {meta.home.club_id, meta.away.club_id}
    players = {p.player_id for p in meta.home_squad + meta.away_squad}
    if scope_id not in (clubs if scope == "team" else players):
        raise HTTPException(404, f"{scope} {scope_id!r} is not in {match_id!r}")
    values = svc.stats.snapshot(meta, period, t).get((scope, scope_id), {})
    profiles = svc.stats.profiles()
    baseline = None
    if scope == "team":
        profile = profiles.clubs[scope_id].model_dump(mode="json")
    else:
        profile = profiles.players[scope_id].model_dump(mode="json")
        base = (svc.stats.baselines() or {}).get(scope_id)
        if base is not None:
            data = svc.stats.match_upto(meta, period, t, frame=False)
            baseline = expected_so_far(data, base, (period, t))
    return {"metrics": dict(sorted(values.items())), "baseline": baseline, "profile": profile}


@router.get("/matches/{match_id}/pitch-control")
def pitch_control(match_id: str, svc: Svc, period: Period, t: Time) -> Json:
    """The team in possession's control surface: 21 rows (y) by 32 columns (x)."""
    meta = svc.meta(match_id)
    frames = svc.store.read_window(match_id, period, max(0.0, t - FRAME_LOOKBACK_S), t)
    if not frames:
        raise HTTPException(404, f"no tracking frame at {period}:{t}")
    before = [e for e in svc.events(match_id) if (e.period, e.t) <= (period, t)]
    attacking = before[-1].team_id if before else meta.home.club_id
    keepers = {meta.home_squad[0].player_id, meta.away_squad[0].player_id}
    right = attacks_right(attacking == meta.home.club_id, period)
    grid = pitch_control_grid(frames[-1], attacking, goalkeepers=keepers, attacks_right=right)
    return {"grid": grid.round(3).tolist(), "attacking_team": attacking}


@router.get("/matches/{match_id}/recap")
def recap(match_id: str, svc: Svc, lang: Lang = "en", persona: Persona | None = None) -> Recap:
    """The full-time recap in ``lang``, or the English one (``lang: "en"``) when no
    translation is stored. ``persona`` is validated, then ignored."""
    svc.meta(match_id)
    found = svc.repo.get_recap(match_id, lang) or svc.repo.get_recap(match_id)
    if found is None:
        raise HTTPException(404, f"no recap for {match_id!r} yet")
    return found


@router.get("/league")
def league_view() -> Json:
    lg = league()
    players = [p.model_dump() for c in lg.clubs for p in lg.squads[c.club_id]]
    return {"clubs": [c.model_dump() for c in lg.clubs], "players": players}
