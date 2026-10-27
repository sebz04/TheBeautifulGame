"""The MatchMind API: REST and SSE over the precomputed matches, live agent runs, and the
MCP stats server at ``/mcp`` (plan Task 21).

Run with ``uv run uvicorn matchmind.api.app:app``. Tests build their own app with
``create_app(repo=..., store=..., settings=..., limiter=..., regenerator=...)``.
"""

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.transport_security import TransportSecuritySettings

from matchmind.agents.orchestrator import ALL_LANGS, Deps, Regenerated, regenerate
from matchmind.agents.runtime import configure_tracing
from matchmind.api import routes_insights, routes_live, routes_matches
from matchmind.api.ratelimit import RateLimiter
from matchmind.api.routes_insights import Regenerator
from matchmind.api.services import Services, app_version
from matchmind.config import Settings, get_settings
from matchmind.mcp_server.server import build_mcp
from matchmind.schemas import Lang, Variant
from matchmind.store.blob import TrackingStore, tracking_store
from matchmind.store.db import Repo

LOCAL_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]  # the Vite dev server
LOCAL_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]


def _warm(svc: Services) -> None:
    """Fill the cheap per-match caches (momentum and replay index: under 1 s a match).
    Realism is not warmed: it is stored at build time, and computing it here would hold
    the GIL for seconds per match and stall live streams."""
    for match_id in svc.repo.list_matches():
        meta = svc.meta(match_id)
        svc.momentum(meta)
        svc.replay_index(meta, routes_live.build_index)


def foundry_regenerator(svc: Services, settings: Settings) -> Regenerator:
    """Live runs on the Foundry deployment, with the stats tools served in-process."""

    async def run(moment_id: str, variant: Variant, lang: Lang) -> Regenerated:
        from azure.identity.aio import DefaultAzureCredential  # noqa: PLC0415
        from mcp import Client  # noqa: PLC0415

        from matchmind.agents.runtime import make_chat_client, stats_tools  # noqa: PLC0415
        from matchmind.agents.verifier import StatsFacts  # noqa: PLC0415

        mcp_server = build_mcp(svc.repo, svc.store)
        async with DefaultAzureCredential() as credential, Client(mcp_server) as mcp:
            client = make_chat_client(settings, credential)
            async with stats_tools(settings, session=mcp.session) as tools:
                deps = Deps(repo=svc.repo, client=client, tools=tools,
                            facts_for=lambda m: StatsFacts(svc.stats, m),
                            langs=ALL_LANGS)  # fmt: skip
                return await regenerate(moment_id, variant, lang, deps)

    return run


def create_app(
    repo: Repo | None = None,
    store: TrackingStore | None = None,
    *,
    warm: bool = False,
    settings: Settings | None = None,
    limiter: RateLimiter | None = None,
    regenerator: Regenerator | None = None,
) -> FastAPI:
    """``warm`` fills the caches in a background thread at startup (the served app)."""
    settings = settings or get_settings()
    svc = Services(repo or Repo(settings.db_url), store or tracking_store(settings))
    mcp_server = build_mcp(svc.repo, svc.store)
    origins = LOCAL_ORIGINS + ([settings.web_origin] if settings.web_origin else [])
    hosts = LOCAL_HOSTS + ([settings.api_host, f"{settings.api_host}:*"]
                           if settings.api_host else [])  # fmt: skip
    mcp_asgi = mcp_server.streamable_http_app(
        streamable_http_path="/mcp",
        transport_security=TransportSecuritySettings(
            allowed_hosts=hosts,
            allowed_origins=[*origins, "http://127.0.0.1:*", "http://localhost:*"],
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if warm:
            app.state.warmer = threading.Thread(target=_warm, args=(svc,), name="warm",
                                                daemon=True)  # fmt: skip
            app.state.warmer.start()
        async with mcp_server.session_manager.run():
            yield

    app = FastAPI(title="MatchMind", version=app_version(), lifespan=lifespan)
    app.state.services = svc
    app.state.limiter = limiter or RateLimiter()
    app.state.regenerator = regenerator or foundry_regenerator(svc, settings)
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type", "Last-Event-ID"])  # fmt: skip
    app.include_router(routes_matches.router)
    app.include_router(routes_insights.router)
    app.include_router(routes_live.router)
    app.mount("/", mcp_asgi)  # last, so it only sees /mcp
    return app


def __getattr__(name: str) -> Any:
    """``app`` is built on first use, so importing this module touches no database. The
    served app sends traces to Application Insights (live agent runs get trace ids)."""
    if name == "app":
        configure_tracing(get_settings())
        globals()["app"] = create_app(warm=True)
        return globals()["app"]
    raise AttributeError(name)
