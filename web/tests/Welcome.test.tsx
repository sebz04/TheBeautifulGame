import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import type { League } from "../src/api/types";
import Welcome from "../src/pages/Welcome";
import { DEFAULT_PREFS } from "../src/state/prefs";
import { useStore } from "../src/state/store";
import clubs from "./fixtures/clubs.json";

const LEAGUE: League = {
  clubs: clubs.map((c) => ({ ...c, formation: "4-3-3" })),
  players: [
    { player_id: "ach-09", name: "Harold Morejo", club_id: "chapinero", number: 9, position: "FW" },
    { player_id: "ach-01", name: "Keeper Uno", club_id: "chapinero", number: 1, position: "GK" },
    { player_id: "ala-14", name: "Jhojan Monero", club_id: "laureles", number: 14, position: "MF" },
  ],
};

function renderAt(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<Welcome />} />
        <Route path="/welcome" element={<Welcome forceSetup />} />
        <Route path="/matches" element={<p>match list</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  useStore.setState({ prefs: { ...DEFAULT_PREFS, sides: {} } });
  vi.spyOn(api, "league").mockResolvedValue(LEAGUE);
});
afterEach(() => vi.restoreAllMocks());

describe("Welcome", () => {
  it("shows the 20 clubs as buttons", async () => {
    renderAt();
    const group = await screen.findByRole("group", { name: /pick your club/i });
    expect(group.querySelectorAll("button")).toHaveLength(20);
  });

  it("saves exactly the choices made and goes to the match list", async () => {
    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: "Atlético Chapinero" }));
    const player = screen.getByRole("combobox", { name: /favorite player/i });
    expect([...player.querySelectorAll("option")].map((o) => o.textContent)).toEqual(["No favorite player", "Harold Morejo", "Keeper Uno"]);
    fireEvent.change(player, { target: { value: "ach-09" } });
    fireEvent.click(screen.getByRole("radio", { name: /scout/i }));
    fireEvent.change(screen.getByRole("combobox", { name: /language/i }), { target: { value: "pt" } });
    fireEvent.click(screen.getByRole("button", { name: /começar|start/i }));
    expect(await screen.findByText("match list")).toBeInTheDocument();
    expect(useStore.getState().prefs).toEqual({
      mode: "scout", focus: "team", lang: "pt", favorite_club_id: "chapinero", favorite_player_id: "ach-09", sides: {},
    });
    expect(JSON.parse(localStorage.getItem("matchmind.prefs")!)).toMatchObject({ favorite_club_id: "chapinero" });
  });

  it("a returning visitor goes straight to the match list; 'Change my setup' brings it back", async () => {
    localStorage.setItem("matchmind.prefs", JSON.stringify({ ...DEFAULT_PREFS, favorite_club_id: "suba" }));
    renderAt("/");
    expect(await screen.findByText("match list")).toBeInTheDocument();
    renderAt("/welcome");
    expect(await screen.findByRole("group", { name: /pick your club/i })).toBeInTheDocument();
  });
});
