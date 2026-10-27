import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Counterfactual } from "../src/api/types";
import FreezeFrame from "../src/components/FreezeFrame";

const CF: Counterfactual = {
  event_id: "e1",
  chosen: { kind: "pass", target_player_id: "p2", end: [40, 20], score: 0.3, pc_prob: 0.91, xt_gain: 0.0 },
  best: { kind: "through", target_player_id: "p3", end: [88, 50], score: 0.5, pc_prob: 0.54, xt_gain: 0.11 },
  gain: 0.2,
  alternatives: [
    { kind: "through", target_player_id: "p3", end: [88, 50], score: 0.5, pc_prob: 0.54, xt_gain: 0.11 },
    { kind: "shot", target_player_id: null, end: [105, 34], score: 0.4, pc_prob: 0.2, xt_gain: 0.06 },
    { kind: "carry", target_player_id: null, end: [70, 40], score: 0.35, pc_prob: 0.8, xt_gain: 0.02 },
  ],
};

const PROPS = {
  cf: CF,
  from: [60, 34] as [number, number],
  frame: null,
  heat: null,
  colors: { home: "#6A1B9A", away: "#E4002B", homeId: "h" },
  names: { p2: "Yeison Oseera", p3: "Jhojan Monero" },
};

describe("FreezeFrame", () => {
  it("draws the real choice dashed and the best one as an arrow", () => {
    const { container } = render(<FreezeFrame {...PROPS} />);
    const real = container.querySelector("[data-line=real]")!;
    const best = container.querySelector("[data-line=best]")!;
    expect(real.getAttribute("stroke-dasharray")).toBeTruthy();
    expect(best.getAttribute("marker-end")).toContain("url(");
  });

  it("compares chance and danger in a scorecard", () => {
    render(<FreezeFrame {...PROPS} />);
    const real = screen.getByRole("group", { name: /what happened/i });
    const best = screen.getByRole("group", { name: /best play/i });
    expect(real).toHaveTextContent("91%");
    expect(real).toHaveTextContent(/no added danger/i);
    expect(best).toHaveTextContent("54%");
    expect(best).toHaveTextContent("+0.11");
    expect(best).toHaveTextContent("Jhojan Monero");
  });

  it("lists up to five other options; choosing one redraws its line", () => {
    const { container } = render(<FreezeFrame {...PROPS} />);
    const others = screen.getByRole("group", { name: /other options/i });
    const buttons = within(others).getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
    expect(buttons.length).toBeLessThanOrEqual(5);
    fireEvent.click(within(others).getByRole("button", { name: /shot/i }));
    const picked = container.querySelector("[data-line=picked]")!;
    expect(picked.getAttribute("x2")).toBe(String(105 * 10));
    expect(within(others).getByRole("button", { name: /shot/i })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("FreezeFrame when the player chose the best option", () => {
  it("says so instead of comparing an option with itself", () => {
    const same = { ...CF, chosen: CF.best };
    render(<FreezeFrame {...PROPS} cf={same} />);
    expect(screen.getByText(/picked the best option/i)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /what happened/i })).not.toBeInTheDocument();
  });
});
