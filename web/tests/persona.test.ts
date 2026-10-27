import { describe, expect, it } from "vitest";

import { personaFor, themeClubFor } from "../src/persona";
import { DEFAULT_PREFS, type Prefs } from "../src/state/prefs";

const MATCH = { match_id: "r01", home: { club_id: "chapinero" }, away: { club_id: "laureles" }, players: ["ach-09", "ala-14"] };
const prefs = (p: Partial<Prefs>): Prefs => ({ ...DEFAULT_PREFS, sides: {}, ...p });

describe("personaFor", () => {
  it("fan of a club in the match: club_fan for it", () => {
    expect(personaFor(prefs({ favorite_club_id: "laureles" }), MATCH)).toEqual({ persona: "club_fan", club_id: "laureles" });
  });

  it("fan whose club isn't playing: asks for a side, then uses it", () => {
    expect(personaFor(prefs({ favorite_club_id: "suba" }), MATCH)).toEqual({ needsSide: true });
    const picked = prefs({ favorite_club_id: "suba", sides: { r01: "chapinero" } });
    expect(personaFor(picked, MATCH)).toEqual({ persona: "club_fan", club_id: "chapinero" });
  });

  it("fan with no club: casual", () => {
    expect(personaFor(prefs({}), MATCH)).toEqual({ persona: "casual" });
  });

  it("scout following the team: analyst", () => {
    expect(personaFor(prefs({ mode: "scout", favorite_club_id: "chapinero" }), MATCH)).toEqual({ persona: "analyst" });
  });

  it("following a player in the match: player_focus, as a fan or a scout", () => {
    for (const mode of ["fan", "scout"] as const) {
      const p = prefs({ mode, focus: "player", favorite_player_id: "ach-09", favorite_club_id: "chapinero" });
      expect(personaFor(p, MATCH)).toEqual({ persona: "player_focus", player_id: "ach-09" });
    }
  });

  it("following a player who isn't in this match: the team rule for the mode", () => {
    expect(personaFor(prefs({ focus: "player", favorite_player_id: "dsu-07", favorite_club_id: "chapinero" }), MATCH)).toEqual({
      persona: "club_fan",
      club_id: "chapinero",
    });
    expect(personaFor(prefs({ mode: "scout", focus: "player", favorite_player_id: "dsu-07" }), MATCH)).toEqual({ persona: "analyst" });
  });
});

describe("themeClubFor", () => {
  it("is the favorite if playing, else the picked side, else none", () => {
    expect(themeClubFor(prefs({ favorite_club_id: "laureles" }), MATCH)).toBe("laureles");
    expect(themeClubFor(prefs({ favorite_club_id: "suba", sides: { r01: "chapinero" } }), MATCH)).toBe("chapinero");
    expect(themeClubFor(prefs({ favorite_club_id: "suba" }), MATCH)).toBeNull();
    expect(themeClubFor(prefs({}), MATCH)).toBeNull();
  });
});
