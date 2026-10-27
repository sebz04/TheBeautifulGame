import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import type { MatchRow, Regenerated } from "../src/api/types";
import AskWhyPanel from "../src/components/AskWhyPanel";
import { defaultPlayer } from "../src/components/PlayerTab";
import { Loading } from "../src/components/Status";
import MatchPicker from "../src/pages/MatchPicker";
import { DEFAULT_PREFS } from "../src/state/prefs";
import { useStore } from "../src/state/store";
import { ROW, WHY } from "./fixtures/insight";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("loading text inside a card", () => {
  it("uses the card's text color, not the page's", () => {
    render(<Loading what="what.evidence" onCard />);
    expect(screen.getByRole("status").className).toContain("text-text ");
    expect(screen.getByRole("status").className).not.toContain("text-text-on-bg");
  });
});

describe("monograms", () => {
  it("use readable text on the club color (El Prado gold gets dark text)", async () => {
    const prado = { club_id: "el-prado", name: "Atlético El Prado", short: "AEP", primary_color: "#FFD700", secondary_color: "#000000", formation: "4-3-3" };
    const row: MatchRow = { match_id: "m", title: "t", home: prado, away: { ...prado, club_id: "x", short: "XXX" }, score: { home: 0, away: 0 }, scenario_id: "s" };
    vi.spyOn(api, "matches").mockResolvedValue([row]);
    useStore.setState({ prefs: { ...DEFAULT_PREFS, sides: {} } });
    render(<MemoryRouter><MatchPicker /></MemoryRouter>);
    const mono = (await screen.findAllByText("AEP"))[0];
    expect(mono.style.color).toBe("rgb(14, 14, 18)");
  });
});

describe("the Player tab's starting player", () => {
  const squad = [{ player_id: "ach-01", name: "A" }, { player_id: "ach-09", name: "B" }];
  it("is the favorite only when they're in this match", () => {
    expect(defaultPlayer(squad, "ach-09", "ach-01")).toBe("ach-09");
    expect(defaultPlayer(squad, "dsu-07", "ach-01")).toBe("ach-01");
    expect(defaultPlayer(squad, null, "ach-01")).toBe("ach-01");
  });
});

describe("Ask why for another insight", () => {
  it("starts fresh and ignores a live answer that arrives for the previous one", async () => {
    vi.spyOn(api, "why").mockResolvedValue(WHY);
    let resolve!: (r: Regenerated) => void;
    vi.spyOn(api, "regenerate").mockReturnValue(new Promise((r) => (resolve = r)));
    const props = { matchId: "m1", variant: { persona: "casual" as const }, lang: "en" as const, addedS: [120, 180] as [number, number], names: {}, onClose: vi.fn() };
    const other = { ...ROW, insight: { ...ROW.insight, insight_id: "other-ins", moment_id: "m1-m009" }, text: { ...ROW.text, headline: "Another moment" } };
    const { rerender } = render(<AskWhyPanel {...props} row={ROW} />);
    fireEvent.click(await screen.findByRole("button", { name: /ask the pundit live/i }));
    rerender(<AskWhyPanel {...props} row={other} />);
    await act(async () => resolve({ insight: ROW.insight, text: { ...ROW.text, headline: "Late answer for the first" }, agent_runs: [], trace_id: null }));
    expect(screen.queryByText("Late answer for the first")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ask the pundit live/i })).toBeEnabled();
  });

  it("brings the panel into view and focuses its heading", async () => {
    vi.spyOn(api, "why").mockResolvedValue(WHY);
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    render(<AskWhyPanel matchId="m1" row={ROW} variant={{ persona: "casual" }} lang="en" addedS={[120, 180]} names={{}} onClose={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 2 })).toHaveFocus();
    expect(scroll).toHaveBeenCalled();
  });
});

describe("a stream that fails for good", () => {
  class DeadEventSource {
    static last: DeadEventSource;
    readyState = 0;
    onerror: (() => void) | null = null;
    onopen = null;
    constructor() {
      DeadEventSource.last = this;
    }
    addEventListener() {}
    close() {}
  }
  beforeEach(() => vi.stubGlobal("EventSource", DeadEventSource));

  it("stops playing and says so", () => {
    useStore.setState({ matchId: null });
    useStore.getState().openMatch("m-dead");
    useStore.getState().play();
    DeadEventSource.last.readyState = 2;
    act(() => DeadEventSource.last.onerror?.());
    expect(useStore.getState().playing).toBe(false);
    expect(useStore.getState().connection).toBe("failed");
  });
});
