// The score at a moment of the replay, from the timeline's goal moments.
import type { Moment, Period, Score } from "../api/types";

export function scoreAt(moments: Moment[], period: Period, t: number, homeId: string): Score {
  const scored = moments.filter((m) => m.kind === "goal" && (m.period < period || (m.period === period && m.t_start <= t)));
  const home = scored.filter((m) => m.team_id === homeId).length;
  return { home, away: scored.length - home };
}
