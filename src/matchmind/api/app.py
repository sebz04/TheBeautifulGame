"""The MatchMind API: REST over the precomputed matches (plan Task 21).

Run with ``uv run uvicorn matchmind.api.app:app``. Tests build their own app with
``create_app(repo=..., store=...)``.
"""

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from matchmind.api import routes_insights, routes_live, routes_matches
from matchmind.api.services import Services, app_version
from matchmind.config import get_settings
from matchmind.store.blob import TrackingStore, tracking_store
from matchmind.store.db import Repo


def _warm(svc: Services) -> None:
    """Fill the cheap per-match caches (momentum and replay index: under 1 s a match).
    Realism is not warmed: it is stored at build time, and computing it here would hold
    the GIL for seconds per match and stall live streams."""
    for match_id in svc.repo.list_matches():
        meta = svc.meta(match_id)
        svc.momentum(meta)
        svc.replay_index(meta, routes_live.build_index)


def create_app(
    repo: Repo | None = None, store: TrackingStore | None = None, *, warm: bool = False
) -> FastAPI:
    """``warm`` fills the caches in a background thread at startup (the served app)."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if warm:
            app.state.warmer = threading.Thread(
                target=_warm, args=(app.state.services,), name="warm", daemon=True
            )
            app.state.warmer.start()
        yield

    app = FastAPI(title="MatchMind", version=app_version(), lifespan=lifespan)
    app.state.services = Services(repo or Repo(settings.db_url), store or tracking_store(settings))
    app.include_router(routes_matches.router)
    app.include_router(routes_insights.router)
    app.include_router(routes_live.router)
    return app


def __getattr__(name: str) -> Any:
    """``app`` is built on first use, so importing this module touches no database."""
    if name == "app":
        globals()["app"] = create_app(warm=True)
        return globals()["app"]
    raise AttributeError(name)
