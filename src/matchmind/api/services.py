"""What the routes share: the store, the stats service, and per-match caches.

The data is precomputed and read-only while the API runs, so a match's events, realism
report, momentum series, and replay index are loaded once and kept.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from matchmind.agents.context import match_names
from matchmind.engine.validate import RealismReport, validate_match
from matchmind.league.league import League, build_league
from matchmind.mcp_server.server import StatsService
from matchmind.pipeline.build_match import LEAGUE_SEED
from matchmind.schemas import Event, MatchData, MatchMeta
from matchmind.stats.team import MomentumSeries, momentum_series
from matchmind.store.blob import TrackingStore
from matchmind.store.db import Repo


def app_version() -> str:
    try:
        return version("matchmind")
    except PackageNotFoundError:  # pragma: no cover - running from a source tree
        return "0.0.0"


class Services:
    def __init__(self, repo: Repo, store: TrackingStore) -> None:
        self.repo, self.store = repo, store
        self.stats = StatsService(repo, store)
        self._events: dict[str, list[Event]] = {}
        self._realism: dict[str, RealismReport] = {}
        self._momentum: dict[str, MomentumSeries] = {}
        self._replay: dict[str, Any] = {}

    def meta(self, match_id: str) -> MatchMeta:
        meta = self.repo.get_match_meta(match_id)
        if meta is None:
            raise HTTPException(404, f"unknown match {match_id!r}")
        return meta

    def events(self, match_id: str) -> list[Event]:
        if match_id not in self._events:
            self._events[match_id] = self.repo.get_events(match_id)
        return self._events[match_id]

    def score(self, meta: MatchMeta) -> dict[str, int]:
        goals = [e.team_id for e in self.events(meta.match_id) if e.type == "goal"]
        return {"home": goals.count(meta.home.club_id), "away": goals.count(meta.away.club_id)}

    def realism(self, meta: MatchMeta) -> RealismReport:
        """The match's realism checks, as stored by ``matchmind build``. A match built
        before that is checked once here (it reads every frame: about 10 s) and saved."""
        mid = meta.match_id
        if mid not in self._realism:
            stored = self.repo.get_realism(mid)
            if stored is None:
                frames = self.store.read_all(mid) if self.store.exists(mid) else []
                data = MatchData(meta=meta, events=self.events(mid), frames=frames)
                report = validate_match(data)
                self.repo.save_realism(mid, report.model_dump())
            else:
                report = RealismReport.model_validate(stored)
            self._realism[mid] = report
        return self._realism[mid]

    def momentum(self, meta: MatchMeta) -> MomentumSeries:
        if meta.match_id not in self._momentum:
            self._momentum[meta.match_id] = momentum_series(
                self.events(meta.match_id), self.stats.grid, meta.home.club_id
            )
        return self._momentum[meta.match_id]

    def replay_index(self, meta: MatchMeta, build: Callable[[Services, MatchMeta], Any]) -> Any:
        """The live replay's message index (``routes_live.build_index``), once per match."""
        if meta.match_id not in self._replay:
            self._replay[meta.match_id] = build(self, meta)
        return self._replay[meta.match_id]

    def names(self, meta: MatchMeta) -> dict[str, str]:
        return match_names(meta)


@cache
def league() -> League:
    return build_league(LEAGUE_SEED)


def _services(request: Request) -> Services:
    svc: Services = request.app.state.services
    return svc


Svc = Annotated[Services, Depends(_services)]
Json = dict[str, Any]
