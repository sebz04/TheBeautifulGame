import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import PlaybackBar from "../src/components/PlaybackBar";

function setup(playing = false) {
  const props = {
    playing,
    speed: 1 as const,
    period: 1 as const,
    t: 600,
    firstHalfS: 47 * 60,
    secondHalfS: 49 * 60,
    onToggle: vi.fn(),
    onSpeed: vi.fn(),
    onSeek: vi.fn(),
  };
  render(<PlaybackBar {...props} />);
  return props;
}

describe("PlaybackBar", () => {
  it("toggles play and pause with Space", () => {
    const p = setup();
    fireEvent.keyDown(screen.getByRole("group", { name: /playback/i }), { key: " " });
    expect(p.onToggle).toHaveBeenCalledTimes(1);
  });

  it("labels the play button by what it does", () => {
    setup(true);
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
  });

  it("changes speed", () => {
    const p = setup();
    fireEvent.click(screen.getByRole("button", { name: "2×" }));
    expect(p.onSpeed).toHaveBeenCalledWith(2);
    expect(screen.getByRole("button", { name: "1×" })).toHaveAttribute("aria-pressed", "true");
  });

  it("seeks across half time with the slider", () => {
    const p = setup();
    const slider = screen.getByRole("slider", { name: /match time/i });
    fireEvent.change(slider, { target: { value: String(47 * 60 + 90) } });
    expect(p.onSeek).toHaveBeenCalledWith(2, 90);
  });

  it("reaches every control by Tab", async () => {
    setup();
    const user = userEvent.setup();
    const seen: string[] = [];
    for (let i = 0; i < 8; i++) {
      await user.tab();
      const el = document.activeElement as HTMLElement;
      seen.push(el.getAttribute("aria-label") ?? el.textContent ?? "");
    }
    expect(seen).toEqual(expect.arrayContaining(["Play", "0.5×", "1×", "2×", "4×", "8×", "Match time"]));
  });
});
