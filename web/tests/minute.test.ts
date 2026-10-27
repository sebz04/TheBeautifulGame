import { describe, expect, it } from "vitest";

import { minuteLabel } from "../src/live/minute";

describe("minuteLabel", () => {
  it("counts the minute being played, like a broadcast clock", () => {
    expect(minuteLabel(1, 0, [120, 180])).toBe("1'");
    expect(minuteLabel(1, 62 * 60 - 1, [120, 180])).toBe("45'"); // clamped outside added time
    expect(minuteLabel(2, 17 * 60 + 30, [120, 180])).toBe("63'");
  });

  it("shows added time as 45+n", () => {
    expect(minuteLabel(1, 46 * 60 + 5, [120, 180])).toBe("45+2'");
    expect(minuteLabel(2, 47 * 60 + 10, [120, 180])).toBe("90+3'");
  });
});
