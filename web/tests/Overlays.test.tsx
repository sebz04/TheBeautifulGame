import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Cue } from "../src/api/types";
import Overlays, { visibleCues } from "../src/components/Overlays";

const cue = (id: string, priority: number, t_in = 100, t_out = 110, kind = "stat_card"): Cue => ({
  cue_id: id, match_id: "m", period: 1, t_in, t_out, kind, priority, payload: { player_id: "p1", value: 9.1 },
}); // prettier-ignore

describe("visibleCues", () => {
  it("shows at most three, highest priority first", () => {
    const cues = [1, 2, 3, 4, 5].map((p) => cue(`c${p}`, p));
    expect(visibleCues(cues, 1, 105).map((c) => c.cue_id)).toEqual(["c5", "c4", "c3"]);
  });

  it("drops cues that have ended or not started, and other periods", () => {
    const cues = [cue("old", 5, 90, 100), cue("now", 1), cue("soon", 5, 106, 120), { ...cue("p2", 5), period: 2 as const }];
    expect(visibleCues(cues, 1, 105).map((c) => c.cue_id)).toEqual(["now"]);
  });

  it("breaks ties by the newer cue", () => {
    expect(visibleCues([cue("a", 3, 100), cue("b", 3, 102)], 1, 105).map((c) => c.cue_id)).toEqual(["b", "a"]);
  });
});

describe("Overlays", () => {
  it("renders exactly three of five active cues", () => {
    const cues = [1, 2, 3, 4, 5].map((p) => cue(`c${p}`, p));
    render(<Overlays cues={cues} period={1} t={105} names={{ p1: "Harold Morejo" }} />);
    expect(screen.getAllByRole("note")).toHaveLength(3);
    expect(screen.getAllByRole("note")[0]).toHaveTextContent("Harold Morejo");
  });
});
