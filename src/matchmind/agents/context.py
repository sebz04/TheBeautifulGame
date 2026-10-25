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


EVENTS_WINDOW_S = 300.0


def moment_context(moment: Moment) -> dict[str, Any]:
    """The moment as agents see it: its fields, the minutes it starts and ends in, and the
    window to read its events from. Moments found from rolling stats (a pressing collapse
    is the instant PPDA crossed its line) can have no events and a zero-length window, so
    the window is at least the last 5 minutes up to the moment's end."""
    t_from = max(0.0, min(moment.t_start, moment.t_end - EVENTS_WINDOW_S))
    return {
        **moment.model_dump(),
        "minute_start": minute_label(moment.period, moment.t_start),
        "minute_end": minute_label(moment.period, moment.t_end),
        "events_window": {"period": moment.period, "t_from": t_from, "t_to": moment.t_end},
    }
