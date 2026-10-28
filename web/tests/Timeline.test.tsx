import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Moment } from "../src/api/types";
import Timeline, { kindLabel, leadIn } from "../src/components/Timeline";

const moment = (id: string, period: 1 | 2, t: number, kind: string): Moment => ({
  moment_id: id, match_id: "m", period, t_start: t, t_end: t + 10, kind, level: "team",
  team_id: "h", player_id: null, trigger_metric: "x", trigger_value: 1, event_ids: [],
}); // prettier-ignore

const MOMENTS = [moment("a", 1, 600, "goal"), moment("b", 2, 300, "red_card"), moment("c", 2, 1200, "big_chance")];

describe("kindLabel", () => {
  it("names moment kinds in plain words", () => {
    expect(kindLabel("player_deviation")).toBe("Player stands out");
    expect(kindLabel("red_card")).toBe("Red card");
  });
});

describe("Timeline", () => {
  it("has one marker per moment, named by kind and minute", () => {
    render(<Timeline moments={MOMENTS} firstHalfS={2820} totalS={5760} period={1} t={0} addedS={[120, 180]} onSeek={vi.fn()} />);
    const markers = screen.getAllByRole("button");
    expect(markers).toHaveLength(3);
    expect(markers[0]).toHaveAccessibleName("Goal, 11'");
    expect(markers[1]).toHaveAccessibleName("Red card, 51'");
  });

  it("starts 5 seconds before the moment, so the viewer sees it happen (note 4)", () => {
    const point = { ...MOMENTS[0], t_start: 2800.8, t_end: 2800.8 };
    expect(leadIn(point)).toBeCloseTo(2795.8);
    expect(leadIn({ ...point, t_start: 2, t_end: 2 })).toBe(0); // never before the kickoff
    const swing = { ...MOMENTS[0], t_start: 30, t_end: 450 }; // a 7-minute momentum swing
    expect(leadIn(swing)).toBe(445); // its last seconds, where the insight lands
  });

  it("seeks to a moment on click or Enter", () => {
    const onSeek = vi.fn();
    render(<Timeline moments={MOMENTS} firstHalfS={2820} totalS={5760} period={1} t={0} addedS={[120, 180]} onSeek={onSeek} />);
    fireEvent.click(screen.getByRole("button", { name: "Red card, 51'" }));
    expect(onSeek).toHaveBeenCalledWith(2, 295);
    screen.getByRole("button", { name: "Big chance, 66'" }).focus();
    fireEvent.keyDown(document.activeElement!, { key: "Enter" });
    fireEvent.click(document.activeElement!); // buttons activate on Enter natively
    expect(onSeek).toHaveBeenLastCalledWith(2, 1195);
  });
});
