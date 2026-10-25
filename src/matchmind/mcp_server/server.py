"""`matchmind-stats`: a read-only MCP server over the stats store, profiles, and baselines.

Every tool returns a JSON-serializable dict with `ref` strings the agents cite: an
event id, a moment id, `match:<id>`, or `metric:<name>@<period>:<t>` for numbers, which
the Verifier recomputes with the same function. Time-scoped tools (`get_team_metrics`,
`get_player_stats`, `get_metric`, `get_player_deviations`) are event-exact: they compute
from the match's data up to (period, t) only, cached per (match_id, period, t), rather
than returning the latest 30 s row, so they never use anything after t. Unknown ids
return `{"error": ...}` instead of failing. Built on the MCP Python SDK 2.x `MCPServer`
(the SDK's new name for FastMCP).
"""

import dataclasses
from collections import OrderedDict
from typing import Any

from mcp.server.mcpserver import MCPServer

from matchmind.config import get_settings
from matchmind.engine.pitch import attacks_right
from matchmind.league.league import build_league
from matchmind.league.season import Season
from matchmind.pipeline.build_match import LEAGUE_SEED
from matchmind.schemas import MatchData, MatchMeta
from matchmind.schemas_profile import Profiles
from matchmind.stats.baselines import PlayerBaseline, player_baselines
from matchmind.stats.counterfactual import counterfactual, decision_frame
from matchmind.stats.deviations import detect_deviations
from matchmind.stats.metrics import PLAYER_METRICS, TEAM_METRICS, snapshot
from matchmind.stats.xt import load_xt
from matchmind.store.blob import TrackingStore, tracking_store
from matchmind.store.db import Repo

TOOL_NAMES = (
    "get_match_summary",
    "get_events",
    "get_team_metrics",
    "get_player_stats",
    "get_moment",
    "get_counterfactual",
    "get_season_context",
    "get_metric",
    "get_player_profile",
    "get_club_profile",
    "get_player_baseline",
    "get_player_deviations",
)
CACHE_SIZE = 256
TOP_ALTERNATIVES = 5
Json = dict[str, Any]


def _ref(name: str, period: int, t: float) -> str:
    return f"metric:{name}@{period}:{t}"


def _error(message: str) -> Json:
    return {"error": message}


class StatsService:
    """The data behind the tools (also usable directly, without MCP)."""

    def __init__(self, repo: Repo, store: TrackingStore) -> None:
        self.repo, self.store = repo, store
        self.grid = load_xt()
        self._profiles: Profiles | None = None
        self._season: Season | None = None
        self._baselines: dict[str, PlayerBaseline] | None = None
        self._snaps: OrderedDict[tuple[str, int, float], dict[tuple[str, str], dict[str, float]]]
        self._snaps = OrderedDict()

    # ---- lazy context ---------------------------------------------------------------------

    def profiles(self) -> Profiles:
        if self._profiles is None:
            from matchmind.league.profiles import build_profiles  # noqa: PLC0415

            self._profiles = build_profiles(build_league(LEAGUE_SEED), seed=LEAGUE_SEED)
        return self._profiles

    def season(self) -> Season | None:
        if self._season is None:
            self._season = self.repo.load_season()
        return self._season

    def baselines(self) -> dict[str, PlayerBaseline] | None:
        if self._baselines is None and self.season() is not None:
            season = self.season()
            assert season is not None
            self._baselines = player_baselines(season, self.profiles())
        return self._baselines

    # ---- match data up to t -----------------------------------------------------------------

    def match_upto(self, meta: MatchMeta, period: int, t: float, frame: bool = True) -> MatchData:
        """Events at or before (period, t), plus the one frame territory needs."""
        events = self.repo.get_events(meta.match_id, t_to=(period, t))
        frames = []
        if frame and events and self.store.exists(meta.match_id):
            last = events[-1]
            frames = self.store.read_window(meta.match_id, last.period, last.t, last.t)
        return MatchData(meta=meta, events=events, frames=frames)

    def snapshot(
        self, meta: MatchMeta, period: int, t: float
    ) -> dict[tuple[str, str], dict[str, float]]:
        key = (meta.match_id, period, float(t))
        if key in self._snaps:
            self._snaps.move_to_end(key)
            return self._snaps[key]
        snap = snapshot(self.match_upto(meta, period, t), self.grid, period, t)
        self._snaps[key] = snap
        if len(self._snaps) > CACHE_SIZE:
            self._snaps.popitem(last=False)
        return snap

    def _scoped(self, values: dict[str, float], period: int, t: float) -> Json:
        return {
            name: {"value": v, "ref": _ref(name, period, t)} for name, v in sorted(values.items())
        }

    # ---- tools --------------------------------------------------------------------------------

    def get_match_summary(self, match_id: str) -> Json:
        meta = self.repo.get_match_meta(match_id)
        if meta is None:
            return _error(f"unknown match_id {match_id!r}")
        goals = self.repo.get_events(match_id, types=("goal",))
        score = {
            "home": sum(g.team_id == meta.home.club_id for g in goals),
            "away": sum(g.team_id == meta.away.club_id for g in goals),
        }
        return {
            "match_id": match_id,
            "scenario_id": meta.scenario_id,
            "seed": meta.seed,
            "home": meta.home.model_dump(),
            "away": meta.away.model_dump(),
            "stadium": meta.stadium,
            "kickoff": meta.kickoff_iso,
            "added_time_s": list(meta.added_time_s),
            "score": score,
            "goal_refs": [g.event_id for g in goals],
            "moments": len(self.repo.list_moments(match_id)),
            "ref": f"match:{match_id}",
        }

    def get_events(
        self, match_id: str, period: int, t_from: float, t_to: float, types: list[str] | None = None
    ) -> Json:
        if self.repo.get_match_meta(match_id) is None:
            return _error(f"unknown match_id {match_id!r}")
        if t_from > t_to:
            return _error(f"empty window: t_from {t_from} > t_to {t_to}")
        evs = self.repo.get_events(match_id, (period, t_from), (period, t_to), types)
        return {
            "match_id": match_id,
            "period": period,
            "events": [e.model_dump() | {"ref": e.event_id} for e in evs],
        }

    def get_team_metrics(self, match_id: str, team_id: str, period: int, t: float) -> Json:
        meta = self.repo.get_match_meta(match_id)
        if meta is None:
            return _error(f"unknown match_id {match_id!r}")
        if team_id not in (meta.home.club_id, meta.away.club_id):
            return _error(f"team {team_id!r} is not in {match_id!r}")
        values = self.snapshot(meta, period, t).get(("team", team_id), {})
        return {
            "match_id": match_id,
            "team_id": team_id,
            "period": period,
            "t": t,
            "metrics": self._scoped(values, period, t),
        }

    def get_player_stats(self, match_id: str, player_id: str, period: int, t: float) -> Json:
        meta = self.repo.get_match_meta(match_id)
        if meta is None:
            return _error(f"unknown match_id {match_id!r}")
        if player_id not in {p.player_id for p in meta.home_squad + meta.away_squad}:
            return _error(f"player {player_id!r} is not in {match_id!r}")
        values = self.snapshot(meta, period, t).get(("player", player_id), {})
        return {
            "match_id": match_id,
            "player_id": player_id,
            "period": period,
            "t": t,
            "on_pitch_yet": bool(values),
            "metrics": self._scoped(values, period, t),
        }

    def get_metric(
        self, match_id: str, name: str, scope: str, scope_id: str, period: int, t: float
    ) -> Json:
        meta = self.repo.get_match_meta(match_id)
        if meta is None:
            return _error(f"unknown match_id {match_id!r}")
        known = {"team": TEAM_METRICS, "player": PLAYER_METRICS}.get(scope)
        if known is None or name not in known:
            return _error(f"unknown metric {name!r} for scope {scope!r}")
        value = self.snapshot(meta, period, t).get((scope, scope_id), {}).get(name)
        return {
            "match_id": match_id,
            "name": name,
            "scope": scope,
            "scope_id": scope_id,
            "period": period,
            "t": t,
            "value": value,
            "ref": _ref(name, period, t),
        }

    def get_moment(self, moment_id: str) -> Json:
        moment = self.repo.get_moment(moment_id)
        if moment is None:
            return _error(f"unknown moment_id {moment_id!r}")
        rows = self.repo.get_snapshot(moment.match_id, moment.period, moment.t_end, "moment")
        at_end: dict[str, Json] = {}
        for r in rows:
            if r.scope == "team":
                at_end.setdefault(r.scope_id, {})[r.name] = {
                    "value": r.value,
                    "ref": _ref(r.name, r.period, r.t),
                }
        return {
            "moment": moment.model_dump(),
            "details": self.repo.moment_details(moment_id),
            "metrics_at_end": at_end,
            "ref": moment_id,
        }

    def get_counterfactual(self, event_id: str) -> Json:
        event = self.repo.get_event(event_id)
        if event is None:
            return _error(f"unknown event_id {event_id!r}")
        if "best_score" not in event.extras:
            return _error(f"{event_id!r} is not a decision (pass, carry, shot, clearance)")
        meta = self.repo.get_match_meta(event.match_id)
        assert meta is not None
        frames = self.store.read_window(event.match_id, event.period, event.t - 1.0, event.t)
        data = MatchData(meta=meta, events=[event], frames=frames)
        keepers = frozenset({meta.home_squad[0].player_id, meta.away_squad[0].player_id})
        right = attacks_right(event.team_id == meta.home.club_id, event.period)
        cf = counterfactual(event, decision_frame(data, event), self.grid, right, keepers)
        top = [dataclasses.asdict(o) for o in cf.alternatives[:TOP_ALTERNATIVES]]
        return {
            "event_id": event_id,
            "chosen": dataclasses.asdict(cf.chosen),
            "best": dataclasses.asdict(cf.best),
            "gain": cf.gain,
            "alternatives": top,
            "ref": event_id,
        }

    def get_season_context(self, entity_id: str) -> Json:
        season = self.season()
        if season is None:
            return _error("no season history stored (run `matchmind build --season`)")
        milestones = season.milestones.get(entity_id, [])
        row = next((s for s in season.standings if s.club_id == entity_id), None)
        if row is not None:
            results = [
                r.model_dump() for r in season.results if entity_id in (r.home_id, r.away_id)
            ]
            position = season.standings.index(row) + 1
            return {
                "club_id": entity_id,
                "position": position,
                "standing": row.model_dump(),
                "results": results,
                "milestones": milestones,
                "ref": f"season:{entity_id}",
            }
        lines = [ln for ln in season.player_lines if ln.player_id == entity_id]
        if not lines:
            return _error(f"unknown club or player {entity_id!r} in the season history")
        counts = ("minutes", "goals", "assists", "shots", "passes", "tackles", "yellow", "red")
        totals = {k: sum(getattr(ln, k) for ln in lines) for k in counts} | {"matches": len(lines)}
        disc = season.discipline.get(entity_id)
        return {
            "player_id": entity_id,
            "totals": totals,
            "milestones": milestones,
            "discipline": disc.model_dump() if disc else None,
            "ref": f"season:{entity_id}",
        }

    def get_player_profile(self, player_id: str) -> Json:
        prof = self.profiles().players.get(player_id)
        if prof is None:
            return _error(f"unknown player_id {player_id!r}")
        return {"profile": prof.model_dump(mode="json"), "ref": f"profile:{player_id}"}

    def get_club_profile(self, club_id: str) -> Json:
        prof = self.profiles().clubs.get(club_id)
        if prof is None:
            return _error(f"unknown club_id {club_id!r}")
        return {"profile": prof.model_dump(mode="json"), "ref": f"profile:{club_id}"}

    def get_player_baseline(self, player_id: str) -> Json:
        baselines = self.baselines()
        if baselines is None:
            return _error("no season history stored (run `matchmind build --season`)")
        base = baselines.get(player_id)
        if base is None:
            return _error(f"unknown player_id {player_id!r}")
        return {"baseline": base.model_dump(), "ref": f"baseline:{player_id}"}

    def get_player_deviations(self, match_id: str, period: int, t: float) -> Json:
        meta = self.repo.get_match_meta(match_id)
        if meta is None:
            return _error(f"unknown match_id {match_id!r}")
        baselines = self.baselines()
        if baselines is None:
            return _error("no season history stored (run `matchmind build --season`)")
        data = self.match_upto(meta, period, t, frame=False)  # sprints need frames: skipped
        devs = detect_deviations(data, baselines, (period, t))
        return {
            "match_id": match_id,
            "period": period,
            "t": t,
            "deviations": [d.model_dump() | {"ref": _ref(d.stat, period, t)} for d in devs],
        }


def build_mcp(repo: Repo, store: TrackingStore) -> MCPServer:
    svc = StatsService(repo, store)
    server = MCPServer(
        "matchmind-stats",
        instructions=(
            "Read-only football match statistics. Cite the `ref` of every number you use. "
            "Times are (period, t) with t in seconds since the start of that half."
        ),
    )
    for name in TOOL_NAMES:
        method = getattr(svc, name)
        server.add_tool(method, name=name, description=(method.__doc__ or name.replace("_", " ")))
    return server


def mcp_app() -> Any:
    """Streamable-HTTP ASGI app (mounted at `/mcp` by the API, Task 21)."""
    settings = get_settings()
    return build_mcp(Repo(settings.db_url), tracking_store(settings)).streamable_http_app()
