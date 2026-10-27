import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import PlayerTab from "../src/components/PlayerTab";

const PLAYERS = [{ player_id: "ach-09", name: "Harold Morejo" }, { player_id: "ach-17", name: "Édison Quimán" }];

afterEach(() => vi.restoreAllMocks());

describe("PlayerTab", () => {
  it("compares each stat with the season expectation so far", async () => {
    vi.spyOn(api, "stats").mockResolvedValue({
      metrics: { passes: 31, shots: 3, goals: 3 },
      baseline: { passes: 30.77, shots: 1.2, goals: 0.31 },
      profile: { player_id: "ach-09" },
    });
    render(<PlayerTab matchId="m1" players={PLAYERS} playerId="ach-09" period={2} t={2400} />);
    const shots = await screen.findByRole("row", { name: /shots/i });
    expect(shots).toHaveTextContent("3");
    expect(shots).toHaveTextContent("1.2");
  });

  it("says when there is no season data", async () => {
    vi.spyOn(api, "stats").mockResolvedValue({ metrics: { passes: 31 }, baseline: null, profile: {} });
    render(<PlayerTab matchId="m1" players={PLAYERS} playerId="ach-17" period={2} t={2400} />);
    expect(await screen.findByText(/no season data/i)).toBeInTheDocument();
  });
});
