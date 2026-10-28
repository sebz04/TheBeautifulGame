"""What agents are told about a match besides the stats tools: names and minute labels.

Agents never see a raw id where a fan would see a name, and never turn seconds into
minutes themselves (Constitution I): code gives them both.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from matchmind.clock import minute_label
from matchmind.schemas import Event, MatchMeta, Moment


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


MAX_WINDOW_EVENTS = 8
# A deviation stat's own events, when its name isn't the event type's plural.
STAT_EVENTS = {"dribbles": "carry", "key_passes": "pass", "progressive_passes": "pass",
               "shots_on_target": "shot", "xg": "shot", "goals": "goal"}  # fmt: skip


def window_event_ids(events: Sequence[Event], moment: Moment) -> list[str]:
    """Evidence for a moment that has no events of its own (TASK-25.2), when the Explainer
    cites none: a player moment's events by that player up to its end, of the stat's own type
    when there are any ("dribbles" -> ``carry``); otherwise the moment's team's events in
    its ``events_window``. The latest ``MAX_WINDOW_EVENTS``, in time order."""
    end = (moment.period, moment.t_end)
    if moment.player_id:
        mine = [e for e in events
                if e.player_id == moment.player_id and (e.period, e.t) <= end]  # fmt: skip
        stat = moment.trigger_metric
        types = {STAT_EVENTS.get(stat, ""), stat, stat[:-1], stat[:-2]}
        typed = [e for e in mine if e.type in types]
        chosen = typed or mine
    else:
        window = moment_context(moment)["events_window"]
        chosen = [
            e for e in events
            if e.period == moment.period and window["t_from"] <= e.t <= window["t_to"]
            and (moment.team_id is None or e.team_id == moment.team_id)
        ]  # fmt: skip
    ordered = sorted(chosen, key=lambda e: (e.period, e.t))
    return [e.event_id for e in ordered[-MAX_WINDOW_EVENTS:]]
