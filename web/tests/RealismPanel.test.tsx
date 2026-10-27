import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RealismPanel, { checkLabel } from "../src/components/RealismPanel";

describe("RealismPanel", () => {
  it("names checks in plain words", () => {
    expect(checkLabel("throw_ins:laureles", { laureles: "Atlético Laureles" })).toBe("Throw ins, Atlético Laureles");
    expect(checkLabel("goals_per_match", {})).toBe("Goals per match");
  });

  it("lists misses first and says how many passed", () => {
    const realism = {
      ok: false,
      checks: [
        { name: "passes:a", value: 500, lo: 350, hi: 650, ok: true },
        { name: "fouls:a", value: 4, lo: 8, hi: 18, ok: false },
      ],
    };
    render(<RealismPanel realism={realism} clubs={{ a: "Club A" }} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog")).toHaveTextContent("passes 1 of 2 checks");
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Fouls, Club A");
    expect(items[0]).toHaveTextContent("outside");
  });
});
