import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "../src/api/client";
import type { Regenerated } from "../src/api/types";
import AskWhyPanel from "../src/components/AskWhyPanel";
import { ROW, WHY } from "./fixtures/insight";

const PROPS = {
  row: ROW,
  matchId: "m1",
  variant: { persona: "club_fan" as const, club_id: "chapinero" },
  lang: "en" as const,
  addedS: [120, 180] as [number, number],
  names: { "ach-09": "Harold Morejo", "ach-17": "Édison Quimán" },
  onClose: vi.fn(),
};

const FRESH: Regenerated = {
  insight: { ...ROW.insight, headline: "Fresh take", trace_id: "t-new" },
  text: { ...ROW.text, headline: "A fresh take for you", body: "Live from the agents." },
  agent_runs: [{ ...WHY.agent_runs[0], run_id: "r9", trace_id: "t-new" }],
  trace_id: "t-new",
};

afterEach(() => vi.restoreAllMocks());

describe("AskWhyPanel", () => {
  it("shows the claims, the cited events by minute, and the agent trace", async () => {
    vi.spyOn(api, "why").mockResolvedValue(WHY);
    render(<AskWhyPanel {...PROPS} />);
    expect(await screen.findByText("xG of 0.777")).toBeInTheDocument();
    expect(screen.getByText(/84'/)).toBeInTheDocument(); // the shot, by minute
    expect(screen.getByText(/explainer/i)).toBeInTheDocument();
    expect(screen.getByText(/t-abc/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /best option/i })).toBeInTheDocument(); // counterfactual arrow
  });

  it("asks the pundit live: progress, then the fresh result beside the stored one", async () => {
    vi.spyOn(api, "why").mockResolvedValue(WHY);
    let resolve!: (r: Regenerated) => void;
    const regen = vi.spyOn(api, "regenerate").mockReturnValue(new Promise((r) => (resolve = r)));
    render(<AskWhyPanel {...PROPS} />);
    const button = await screen.findByRole("button", { name: /ask the pundit live/i });
    fireEvent.click(button);
    fireEvent.click(button); // a double click sends one request
    expect(regen).toHaveBeenCalledTimes(1);
    expect(regen).toHaveBeenCalledWith("m1", { moment_id: "m1-m005", persona: "club_fan", lang: "en", club_id: "chapinero" });
    expect(screen.getByRole("status")).toHaveTextContent(/working/i);
    expect(button).toBeDisabled();
    await act(async () => resolve(FRESH));
    expect(screen.getByText("A fresh take for you")).toBeInTheDocument();
    expect(screen.getByText(/t-new/)).toBeInTheDocument();
    expect(screen.getByText(ROW.text.headline)).toBeInTheDocument(); // the stored one stays
  });

  it("explains the wait when the live limit is reached", async () => {
    vi.spyOn(api, "why").mockResolvedValue(WHY);
    vi.spyOn(api, "regenerate").mockRejectedValue(new ApiError(429, "too many live runs; try again later", 1500));
    render(<AskWhyPanel {...PROPS} />);
    fireEvent.click(await screen.findByRole("button", { name: /ask the pundit live/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/try again in 25 min/i);
    expect(screen.getByText("xG of 0.777")).toBeInTheDocument(); // the panel still works
  });

  it("says when the agents time out", async () => {
    vi.spyOn(api, "why").mockResolvedValue(WHY);
    vi.spyOn(api, "regenerate").mockRejectedValue(new ApiError(504, "the agents took too long"));
    render(<AskWhyPanel {...PROPS} />);
    fireEvent.click(await screen.findByRole("button", { name: /ask the pundit live/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/took too long/i);
    expect(screen.getByRole("button", { name: /ask the pundit live/i })).toBeEnabled();
  });
});

describe("runSummary", () => {
  it("groups runs by agent and counts template fallbacks", async () => {
    const { runSummary } = await import("../src/components/AskWhyPanel");
    const run = WHY.agent_runs[0];
    const lines = runSummary([
      { ...run, run_id: "1", agent: "explainer", latency_ms: 4000 },
      { ...run, run_id: "2", agent: "explainer", latency_ms: 6000, attempts: 2 },
      { ...run, run_id: "3", agent: "verifier", latency_ms: 1500 },
      { ...run, run_id: "4", agent: "template:personalizer", latency_ms: 0, status: "fallback" },
    ]);
    expect(lines).toEqual(["explainer: 2 runs, 10.0 s, 1 retry", "verifier: 1 run, 1.5 s", "template (personalizer): used 1 time"]);
  });
});
