"""Engine entry point: dispatches to the engine level."""

from typing import Literal

from matchmind.engine.baseline import simulate_baseline
from matchmind.engine.coupled import simulate_coupled
from matchmind.schemas import MatchData, MatchMeta
from matchmind.schemas_profile import Profiles


def simulate_match(
    meta: MatchMeta,
    scenario: object | None = None,
    level: Literal[1, 3] = 3,
    tracking: bool = True,
    profiles: Profiles | None = None,
) -> MatchData:
    """`scenario` is typed `object` until TASK-10 defines `Scenario`; it is ignored for now.

    `tracking=False` skips building frames (events are identical); for training and
    season history, where positions are not needed. `profiles` (level 3) turns on the
    modifier layer; without it every player and team plays with neutral modifiers.
    """
    if level == 1:
        return simulate_baseline(meta, tracking=tracking)
    return simulate_coupled(meta, tracking=tracking, profiles=profiles)
