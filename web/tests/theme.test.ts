import { describe, expect, it } from "vitest";

import { NEUTRAL_THEME, clubTheme, contrast } from "../src/design/theme";
import clubs from "./fixtures/clubs.json";

const AA = 4.5;

function passesAA(vars: Record<string, string>): void {
  expect(contrast(vars["--mm-text"], vars["--mm-surface"])).toBeGreaterThanOrEqual(AA);
  expect(contrast(vars["--mm-text-on-bg"], vars["--mm-bg"])).toBeGreaterThanOrEqual(AA);
  expect(contrast(vars["--mm-on-accent"], vars["--mm-accent"])).toBeGreaterThanOrEqual(AA);
  // The accent is drawn on cards (large minutes, borders, markers): 3:1 is AA for those.
  expect(contrast(vars["--mm-accent"], vars["--mm-surface"])).toBeGreaterThanOrEqual(3);
  // Tabs and switch tracks sit on a deeper shade of the club color.
  expect(contrast(vars["--mm-text-on-deep"], vars["--mm-bg-deep"])).toBeGreaterThanOrEqual(AA);
}

describe("contrast", () => {
  it("matches the WCAG ratios", () => {
    expect(contrast("#000000", "#FFFFFF")).toBeCloseTo(21, 2);
    expect(contrast("#777777", "#FFFFFF")).toBeCloseTo(4.48, 2);
    expect(contrast("#FFFFFF", "#777777")).toBeCloseTo(4.48, 2); // order doesn't matter
  });
});

describe("clubTheme", () => {
  for (const club of clubs) {
    for (const surface of ["dark", "light"] as const) {
      it(`${club.name} on ${surface} cards passes AA`, () => {
        passesAA(clubTheme(club, surface));
      });
    }
  }

  it("keeps the club's color as the page field", () => {
    const chapinero = clubs.find((c) => c.club_id === "chapinero")!;
    expect(clubTheme(chapinero, "dark")["--mm-bg"]).toBe("#6A1B9A");
    const prado = clubs.find((c) => c.club_id === "el-prado")!;
    const vars = clubTheme(prado, "light");
    expect(vars["--mm-bg"]).toBe("#FFD700");
    expect(contrast(vars["--mm-text-on-bg"], "#000000")).toBeLessThan(1.5); // near-black
  });

  it("the neutral theme passes AA", () => {
    passesAA(NEUTRAL_THEME);
  });
});
