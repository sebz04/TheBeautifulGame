import { describe, expect, it } from "vitest";

import type { Moment } from "../src/api/types";
import { scoreAt } from "../src/live/score";

const goal = (period: 1 | 2, t: number, team_id: string): Moment => ({
  moment_id: `g${period}${t}`, match_id: "m", period, t_start: t, t_end: t + 5, kind: "goal", level: "player",
  team_id, player_id: "p", trigger_metric: "goals", trigger_value: 1, event_ids: [],
}); // prettier-ignore

describe("scoreAt", () => {
  const moments = [goal(1, 2800, "away"), goal(2, 1064, "home"), goal(2, 1143, "home"), { ...goal(2, 1200, "home"), kind: "big_chance" }];

  it("counts only goals scored by then", () => {
    expect(scoreAt(moments, 1, 0, "home")).toEqual({ home: 0, away: 0 });
    expect(scoreAt(moments, 1, 2800, "home")).toEqual({ home: 0, away: 1 });
    expect(scoreAt(moments, 2, 1100, "home")).toEqual({ home: 1, away: 1 });
    expect(scoreAt(moments, 2, 3000, "home")).toEqual({ home: 2, away: 1 });
  });
});
