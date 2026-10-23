"""Engine entry point: dispatches to the engine level."""

from typing import Literal

from matchmind.engine.baseline import simulate_baseline
from matchmind.engine.coupled import ENGINE_VERSION as COUPLED_VERSION
from matchmind.engine.coupled import simulate_coupled
from matchmind.engine.lineup import ENGINE_VERSION as BASELINE_VERSION
from matchmind.engine.scenario import Scenario
from matchmind.schemas import MatchData, MatchMeta
from matchmind.schemas_profile import Profiles


def engine_version(level: Literal[1, 3]) -> str:
    return BASELINE_VERSION if level == 1 else COUPLED_VERSION


def simulate_match(
    meta: MatchMeta,
    scenario: Scenario | None = None,
    level: Literal[1, 3] = 3,
    tracking: bool = True,
    profiles: Profiles | None = None,
) -> MatchData:
    """Level 3 (with the level-4 tactics, set pieces, and scenario beats) or level 1.

    `tracking=False` skips building frames (events are identical); for training and
    season history, where positions are not needed. `profiles` turns on the modifier
    layer, club tactics, roles, and technical ratings; without it every player and team
    is neutral. `scenario` beats bias the match (level 3 only; level 1 ignores them).
    """
    if level == 1:
        return simulate_baseline(meta, tracking=tracking)
    return simulate_coupled(meta, tracking=tracking, profiles=profiles, scenario=scenario)
