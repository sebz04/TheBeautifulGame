import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import MomentumChart from "../src/components/MomentumChart";
import Pitch from "../src/components/Pitch";
import Timeline from "../src/components/Timeline";
import { setLang } from "../src/i18n/i18n";

describe("right-to-left", () => {
  it("Arabic flips the page but never the pitch, timeline, or chart", () => {
    setLang("ar");
    expect(document.documentElement).toHaveAttribute("dir", "rtl");
    const { container } = render(
      <>
        <Pitch colors={{ home: "#6A1B9A", away: "#E4002B", homeId: "h" }} label="pitch" />
        <Timeline moments={[]} firstHalfS={2820} totalS={5760} period={1} t={0} addedS={[120, 180]} onSeek={vi.fn()} />
        <MomentumChart points={[]} firstHalfS={2820} totalS={5760} period={1} t={0} homeName="A" awayName="B" />
      </>,
    );
    const physical = container.querySelectorAll("[dir]");
    expect(physical.length).toBeGreaterThanOrEqual(3);
    physical.forEach((el) => expect(el).toHaveAttribute("dir", "ltr"));
    setLang("en");
  });
});

describe("numbers in right-to-left text", () => {
  it("minutes, speeds, and the match-time slider stay left to right", async () => {
    const { default: InsightCard } = await import("../src/components/InsightCard");
    const { default: PlaybackBar } = await import("../src/components/PlaybackBar");
    const { ROW } = await import("./fixtures/insight");
    setLang("ar");
    const { getByText, getByRole } = render(
      <>
        <InsightCard row={ROW} minute="84'" onAskWhy={vi.fn()} onBestPlay={vi.fn()} />
        <PlaybackBar playing={false} speed={1} period={2} t={2300} firstHalfS={2820} secondHalfS={2940} onToggle={vi.fn()} onSpeed={vi.fn()} onSeek={vi.fn()} />
      </>,
    );
    expect(getByText("84'")).toHaveAttribute("dir", "ltr");
    expect(getByText("2×")).toHaveAttribute("dir", "ltr");
    expect(getByRole("slider")).toHaveAttribute("dir", "ltr");
    setLang("en");
  });
});
