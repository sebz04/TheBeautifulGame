"""Engine entry point: dispatches to the engine level."""

from typing import Literal

from matchmind.engine.baseline import simulate_baseline
from matchmind.schemas import MatchData, MatchMeta


def simulate_match(
    meta: MatchMeta, scenario: object | None = None, level: Literal[1, 3] = 3
) -> MatchData:
    """`scenario` is typed `object` until TASK-10 defines `Scenario`; level 1 ignores it."""
    if level == 1:
        return simulate_baseline(meta)
    raise NotImplementedError("engine level 3 arrives in TASK-9")
