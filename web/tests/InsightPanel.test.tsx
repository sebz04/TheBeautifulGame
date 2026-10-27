import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { InsightRow, Moment } from "../src/api/types";
import InsightPanel, { insightsSoFar } from "../src/components/InsightPanel";
import { ROW } from "./fixtures/insight";

const moment = (id: string, period: 1 | 2, t_end: number): Moment => ({
  moment_id: id, match_id: "m1", period, t_start: t_end - 20, t_end, kind: "goal", level: "team",
  team_id: "h", player_id: null, trigger_metric: "x", trigger_value: 1, event_ids: [],
}); // prettier-ignore
const row = (id: string, headline: string): InsightRow => ({
  ...ROW, insight: { ...ROW.insight, insight_id: `${id}-ins`, moment_id: id }, text: { ...ROW.text, headline },
}); // prettier-ignore

const MOMENTS = { a: moment("a", 1, 600), b: moment("b", 2, 300), c: moment("c", 2, 2000) };
const ROWS = [row("c", "Third"), row("a", "First"), row("b", "Second")];

describe("InsightPanel", () => {
  it("shows only insights whose moment has ended, newest first", () => {
    expect(insightsSoFar(ROWS, MOMENTS, 2, 400).map((r) => r.text.headline)).toEqual(["Second", "First"]);
    expect(insightsSoFar(ROWS, MOMENTS, 1, 100)).toEqual([]);
  });

  it("puts the newest on top and lists the earlier ones; an earlier one can come back to the top", () => {
    render(<InsightPanel rows={ROWS} moments={MOMENTS} period={2} t={2100} addedS={[120, 180]} onAskWhy={vi.fn()} onBestPlay={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Third");
    fireEvent.click(screen.getByRole("button", { name: /First/ }));
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("First");
  });

  it("invites the viewer to press play before the first insight", () => {
    render(<InsightPanel rows={ROWS} moments={MOMENTS} period={1} t={0} addedS={[120, 180]} onAskWhy={vi.fn()} onBestPlay={vi.fn()} />);
    expect(screen.getByText(/your pundit is watching/i)).toBeInTheDocument();
  });
});
