"""Shared helpers for agent tests: stand-in MCP tools that record their calls."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from agent_framework import FunctionTool, tool

from matchmind.schemas import Moment


def moment(i: int, **overrides: Any) -> Moment:
    base: dict[str, Any] = {
        "moment_id": f"m{i}",
        "match_id": "x1",
        "period": 1,
        "t_start": 60.0 * i,
        "t_end": 60.0 * i + 30,
        "kind": "big_chance",
        "level": "team",
        "team_id": "home",
        "player_id": None,
        "trigger_metric": "xg",
        "trigger_value": 0.4,
        "event_ids": [f"x1-e{i:05d}"],
    }
    return Moment(**{**base, **overrides})


class StatsStub:
    """Stand-ins for a few MCP stats tools, with the same names and argument names."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def tools(self) -> list[FunctionTool]:
        calls = self.calls

        @tool
        def get_moment(moment_id: str) -> str:
            """The moment, its details and team metrics at its end."""
            calls.append(("get_moment", {"moment_id": moment_id}))
            return json.dumps({"moment_id": moment_id, "ref": moment_id, "ppda": 7.5})

        @tool
        def get_counterfactual(event_id: str) -> str:
            """The chosen option against the best one for a decision event."""
            calls.append(("get_counterfactual", {"event_id": event_id}))
            return json.dumps({"event_id": event_id, "gain": 0.031, "ref": event_id})

        @tool
        def get_team_metrics(match_id: str, team_id: str, period: int, t: float) -> str:
            """Team metrics at (period, t)."""
            calls.append(("get_team_metrics", {"match_id": match_id, "period": period, "t": t}))
            return json.dumps({"ppda": 7.5, "ref": f"metric:ppda@{period}:{t}"})

        return [get_moment, get_counterfactual, get_team_metrics]


@pytest.fixture
def stats() -> StatsStub:
    return StatsStub()


def json_reply(payload: Any) -> Callable[..., str]:
    return lambda *_: json.dumps(payload)
