import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import type { MatchRow } from "../src/api/types";
import MatchPicker from "../src/pages/MatchPicker";
import { useStore } from "../src/state/store";
import { DEFAULT_PREFS } from "../src/state/prefs";

const club = (club_id: string, name: string, primary_color = "#123456") => ({
  club_id,
  name,
  short: club_id.slice(0, 3).toUpperCase(),
  primary_color,
  secondary_color: "#FFFFFF",
  formation: "4-3-3",
});

const ROWS: MatchRow[] = [
  { match_id: "r01-suba-v-belen", title: "Deportivo Suba v Deportivo Belén", home: club("suba", "Deportivo Suba"),
    away: club("belen", "Deportivo Belén"), score: { home: 1, away: 0 }, scenario_id: "a" },
  { match_id: "r02-chapinero-v-laureles", title: "Atlético Chapinero v Atlético Laureles",
    home: club("chapinero", "Atlético Chapinero"), away: club("laureles", "Atlético Laureles"),
    score: { home: 3, away: 2 }, scenario_id: "b" },
  { match_id: "r03-manga-v-chipre", title: "Manga Fútbol Club v Deportivo Chipre", home: club("manga", "Manga Fútbol Club"),
    away: club("chipre", "Deportivo Chipre"), score: { home: 0, away: 0 }, scenario_id: "c" },
];

function renderPicker() {
  return render(
    <MemoryRouter>
      <MatchPicker />
    </MemoryRouter>,
  );
}

beforeEach(() => useStore.setState({ prefs: { ...DEFAULT_PREFS, favorite_club_id: "chapinero" } }));
afterEach(() => vi.restoreAllMocks());

describe("MatchPicker", () => {
  it("lists the fan's club's matches first", async () => {
    vi.spyOn(api, "matches").mockResolvedValue(ROWS);
    renderPicker();
    const links = within(await screen.findByRole("list")).getAllByRole("link");
    expect(links[0]).toHaveTextContent("Atlético Chapinero");
    expect(links[0]).toHaveAttribute("href", "/match/r02-chapinero-v-laureles");
    expect(links).toHaveLength(3);
  });

  it("shows a loading state, then the list", async () => {
    let resolve!: (rows: MatchRow[]) => void;
    vi.spyOn(api, "matches").mockReturnValue(new Promise((r) => (resolve = r)));
    renderPicker();
    expect(screen.getByRole("status")).toHaveTextContent(/loading/i);
    resolve(ROWS);
    await screen.findByRole("list");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows an error with a retry button", async () => {
    const spy = vi.spyOn(api, "matches").mockRejectedValueOnce(new Error("offline")).mockResolvedValue(ROWS);
    renderPicker();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/couldn't load/i);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    expect(within(await screen.findByRole("list")).getAllByRole("link")).toHaveLength(3);
  });
});
