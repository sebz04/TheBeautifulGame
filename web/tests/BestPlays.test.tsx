import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import type { InsightRow, MatchDetail, Moment } from "../src/api/types";
import { bestPlayMoments } from "../src/pages/BestPlays";
import BestPlays from "../src/pages/BestPlays";
import { DEFAULT_PREFS } from "../src/state/prefs";
import { useStore } from "../src/state/store";
import { ROW, WHY } from "./fixtures/insight";

const moment = (id: string, period: 1 | 2, t_end: number, kind = "big_chance"): Moment => ({
  moment_id: id, match_id: "m1", period, t_start: t_end - 20, t_end, kind, level: "team",
  team_id: "chapinero", player_id: null, trigger_metric: "x", trigger_value: 1, event_ids: [],
}); // prettier-ignore
const row = (id: string, headline: string, best: string | null): InsightRow => ({
  ...ROW, insight: { ...ROW.insight, insight_id: `${id}-ins`, moment_id: id }, text: { ...ROW.text, headline }, best_play_event_id: best,
}); // prettier-ignore

const MOMENTS = [moment("a", 1, 600), moment("b", 2, 300), moment("c", 2, 2000), moment("g", 2, 100, "goal")];
const ROWS = [row("a", "Early chance", "e-a"), row("b", "Second-half chance", "e-b"), row("c", "Late chance", "e-c"), row("x", "No decision", null)];

const club = (club_id: string, name: string) => ({ club_id, name, short: name.slice(0, 3).toUpperCase(), primary_color: "#6A1B9A", secondary_color: "#FFFFFF", formation: "4-3-3" });
const MATCH = {
  match_id: "m1", home: club("chapinero", "Atlético Chapinero"), away: club("laureles", "Atlético Laureles"),
  home_squad: [], away_squad: [], added_time_s: [120, 180], score: { home: 3, away: 2 }, realism: { checks: [], ok: true },
} as unknown as MatchDetail; // prettier-ignore

class FakeEventSource {
  static all: FakeEventSource[] = [];
  closed = false;
  readyState = 1;
  onerror = null;
  onopen = null;
  constructor(readonly url: string) {
    FakeEventSource.all.push(this);
  }
  addEventListener() {}
  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  FakeEventSource.all = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.spyOn(api, "match").mockResolvedValue(MATCH);
  vi.spyOn(api, "timeline").mockResolvedValue({ moments: MOMENTS, momentum: [] });
  vi.spyOn(api, "insights").mockResolvedValue(ROWS);
  vi.spyOn(api, "league").mockResolvedValue({ clubs: [], players: [] });
  vi.spyOn(api, "why").mockResolvedValue(WHY);
  vi.spyOn(api, "tracking").mockResolvedValue({ frames: [] });
  vi.spyOn(api, "pitchControl").mockResolvedValue({ grid: [[0.5]], attacking_team: "chapinero" });
  useStore.setState({ matchId: null, prefs: { ...DEFAULT_PREFS, sides: {}, favorite_club_id: "chapinero" } });
  useStore.getState().openMatch("m1");
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/match/:id/best-plays" element={<BestPlays />} />
        <Route path="/match/:id" element={<p>live match page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("bestPlayMoments", () => {
  it("keeps insights with a best play whose moment has ended, newest first", () => {
    const byId = Object.fromEntries(MOMENTS.map((m) => [m.moment_id, m]));
    expect(bestPlayMoments(ROWS, byId, 2, 400).map((r) => r.text.headline)).toEqual(["Second-half chance", "Early chance"]);
  });
});

describe("BestPlays", () => {
  it("lists only best-play moments up to the replay time", async () => {
    useStore.getState().seek(2, 400);
    renderAt("/match/m1/best-plays");
    const list = await screen.findByRole("list", { name: /moments so far/i });
    expect(list).toHaveTextContent("Second-half chance");
    expect(list).toHaveTextContent("Early chance");
    expect(list).not.toHaveTextContent("Late chance");
  });

  it("keeps the live match playing: the strip follows the clock, and the stream stays open", async () => {
    useStore.getState().play();
    renderAt("/match/m1/best-plays");
    const strip = await screen.findByRole("region", { name: /live match/i });
    act(() => useStore.setState({ period: 2, t: 150 }));
    expect(strip).toHaveTextContent("48'");
    expect(strip).toHaveTextContent("1–0"); // the 46' goal (moment g) has happened
    expect(FakeEventSource.all.at(-1)!.closed).toBe(false);
  });

  it("goes back to the live match", async () => {
    renderAt("/match/m1/best-plays");
    fireEvent.click(await screen.findByRole("link", { name: /back to live/i }));
    expect(await screen.findByText("live match page")).toBeInTheDocument();
  });
});
