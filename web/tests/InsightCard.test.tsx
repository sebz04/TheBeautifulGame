import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import InsightCard from "../src/components/InsightCard";
import { ROW } from "./fixtures/insight";

describe("InsightCard", () => {
  it("shows the fan's text, the minute, and the confidence", () => {
    render(<InsightCard row={ROW} minute="84'" onAskWhy={vi.fn()} onBestPlay={vi.fn()} />);
    expect(screen.getByRole("heading", { name: ROW.text.headline })).toBeInTheDocument();
    expect(screen.getByText(ROW.text.body)).toBeInTheDocument();
    expect(screen.getByText("84'")).toBeInTheDocument();
    expect(screen.getByText(/confidence/i)).toHaveTextContent(/high/i);
  });

  it("offers Ask why, and Show best play only when there is one", () => {
    const onAskWhy = vi.fn();
    const onBestPlay = vi.fn();
    const { rerender } = render(<InsightCard row={ROW} minute="84'" onAskWhy={onAskWhy} onBestPlay={onBestPlay} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask why" }));
    fireEvent.click(screen.getByRole("button", { name: "Show best play" }));
    expect(onAskWhy).toHaveBeenCalledTimes(1);
    expect(onBestPlay).toHaveBeenCalledWith("m1-e01200");
    rerender(<InsightCard row={{ ...ROW, best_play_event_id: null }} minute="84'" onAskWhy={onAskWhy} onBestPlay={onBestPlay} />);
    expect(screen.queryByRole("button", { name: "Show best play" })).not.toBeInTheDocument();
  });

  it("marks a template text as a standard summary", () => {
    const row = { ...ROW, text: { ...ROW.text, source: "template" as const } };
    render(<InsightCard row={row} minute="84'" onAskWhy={vi.fn()} onBestPlay={vi.fn()} />);
    expect(screen.getByText(/standard summary/i)).toBeInTheDocument();
  });

  it("sets the text direction for Arabic", () => {
    const row = { ...ROW, text: { ...ROW.text, lang: "ar" as const, dir: "rtl" as const } };
    render(<InsightCard row={row} minute="84'" onAskWhy={vi.fn()} onBestPlay={vi.fn()} />);
    expect(screen.getByRole("article")).toHaveAttribute("dir", "rtl");
    expect(screen.getByRole("article")).toHaveAttribute("lang", "ar");
  });
});
