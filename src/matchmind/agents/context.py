"""What agents are told about a match besides the stats tools: names and minute labels.

Agents never see a raw id where a fan would see a name, and never turn seconds into
minutes themselves (Constitution I): code gives them both.
"""

from __future__ import annotations

from typing import Any

from matchmind.clock import minute_label
from matchmind.schemas import MatchMeta, Moment


def match_names(meta: MatchMeta) -> dict[str, str]:
    """Display name for every club and player id in the match."""
    names = {meta.home.club_id: meta.home.name, meta.away.club_id: meta.away.name}
    names |= {p.player_id: p.name for p in [*meta.home_squad, *meta.away_squad]}
    return names


def moment_context(moment: Moment) -> dict[str, Any]:
    """The moment as agents see it: its fields plus the minutes it starts and ends in."""
    return {
        **moment.model_dump(),
        "minute_start": minute_label(moment.period, moment.t_start),
        "minute_end": minute_label(moment.period, moment.t_end),
    }
