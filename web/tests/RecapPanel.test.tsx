import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import type { Recap } from "../src/api/types";
import RecapPanel from "../src/components/RecapPanel";

const recap = (lang: Recap["lang"], title: string): Recap => ({
  match_id: "m1", title, paragraphs: ["p"], key_numbers: [], verified: true, source: "agent", lang,
}); // prettier-ignore

afterEach(() => vi.restoreAllMocks());

describe("RecapPanel", () => {
  it("shows the recap in the fan's language, right to left for Arabic", async () => {
    vi.spyOn(api, "recap").mockResolvedValue(recap("ar", "نهاية المباراة"));
    render(<RecapPanel matchId="m1" lang="ar" />);
    const title = await screen.findByText("نهاية المباراة");
    expect(title.closest("article")).toHaveAttribute("dir", "rtl");
    expect(title.closest("article")).toHaveAttribute("lang", "ar");
    expect(screen.queryByText(/English/)).toBeNull();
  });

  it("says so when only the English recap exists", async () => {
    vi.spyOn(api, "recap").mockResolvedValue(recap("en", "Chapinero turn it around"));
    render(<RecapPanel matchId="m1" lang="es" />);
    const title = await screen.findByText("Chapinero turn it around");
    expect(title.closest("article")).toHaveAttribute("lang", "en");
    expect(screen.getByText(/English/)).toBeInTheDocument();
  });
});
