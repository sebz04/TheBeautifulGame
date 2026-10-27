import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import PersonaBar from "../src/components/PersonaBar";
import { DEFAULT_PREFS } from "../src/state/prefs";
import { useStore } from "../src/state/store";

const PROPS = { clubName: "Atlético Chapinero", playerName: "Harold Morejo" };

beforeEach(() => useStore.setState({ prefs: { ...DEFAULT_PREFS, sides: {}, favorite_club_id: "chapinero", favorite_player_id: "ach-09" } }));

describe("PersonaBar", () => {
  it("has two switches, each with exactly one choice pressed, labeled with the names", () => {
    render(<PersonaBar {...PROPS} />);
    const follow = screen.getByRole("group", { name: /team or your player/i });
    const mode = screen.getByRole("group", { name: /fan or a scout/i });
    for (const g of [follow, mode]) {
      const pressed = [...g.querySelectorAll("button")].filter((b) => b.getAttribute("aria-pressed") === "true");
      expect(pressed).toHaveLength(1);
    }
    expect(screen.getByRole("button", { name: "Atlético Chapinero" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Harold Morejo" })).toHaveAttribute("aria-pressed", "false");
  });

  it("switching updates the saved preferences", () => {
    render(<PersonaBar {...PROPS} />);
    fireEvent.click(screen.getByRole("button", { name: "Harold Morejo" }));
    fireEvent.click(screen.getByRole("button", { name: "Scout" }));
    expect(useStore.getState().prefs).toMatchObject({ focus: "player", mode: "scout" });
  });

  it("changing the language updates the preference", () => {
    render(<PersonaBar {...PROPS} />);
    fireEvent.change(screen.getByRole("combobox", { name: /language/i }), { target: { value: "es" } });
    expect(useStore.getState().prefs.lang).toBe("es");
  });

  it("without a favorite player, the player side is disabled", () => {
    useStore.setState({ prefs: { ...DEFAULT_PREFS, sides: {}, favorite_club_id: "chapinero" } });
    render(<PersonaBar clubName="Atlético Chapinero" playerName={null} />);
    expect(screen.getByRole("button", { name: /player/i })).toBeDisabled();
  });
});
