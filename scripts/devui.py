"""Show the insight workflow in Agent Framework DevUI (development only; used for the video).

Usage: uv run python scripts/devui.py [--port 8080]

Opens the graph analyst → explainer_verifier → narrative → personalizer_verifier. Running a
window from the UI needs the stats tools at `MATCHMIND_MCP_URL` (the API serves them at
`/mcp`, TASK-21), `az login`, and the Foundry settings in `.env`. The input is a
`WindowJob` (match_id, period, t_from, t_to in seconds).
"""

from __future__ import annotations

import argparse
from functools import cache

from agent_framework.devui import serve

from matchmind.agents.orchestrator import Deps, build_workflow
from matchmind.agents.runtime import make_chat_client, stats_tools
from matchmind.agents.verifier import StatsFacts
from matchmind.config import get_settings
from matchmind.mcp_server.server import StatsService
from matchmind.store.blob import tracking_store
from matchmind.store.db import Repo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8080)
    port = parser.parse_args().port
    settings = get_settings()
    repo = Repo(settings.db_url)
    stats = StatsService(repo, tracking_store(settings))

    @cache
    def facts_for(match_id: str) -> StatsFacts:
        return StatsFacts(stats, match_id)

    deps = Deps(repo=repo, client=make_chat_client(settings), tools=stats_tools(settings),
                facts_for=facts_for)  # fmt: skip
    serve(entities=[build_workflow(deps)], port=port, auto_open=True)


if __name__ == "__main__":
    main()
