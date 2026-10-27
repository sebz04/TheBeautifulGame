import { describe, expect, it } from "vitest";

import { DEFAULT_PREFS, loadPrefs, savePrefs, type Prefs } from "../src/state/prefs";

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, v),
  };
}

function throwingStorage(): Storage {
  const fail = () => {
    throw new DOMException("blocked", "SecurityError");
  };
  return { length: 0, clear: fail, getItem: fail, key: fail, removeItem: fail, setItem: fail };
}

const MINE: Prefs = {
  mode: "scout",
  focus: "player",
  lang: "ar",
  favorite_club_id: "chapinero",
  favorite_player_id: "ach-09",
  sides: { "r11-x": "suba" },
};

describe("prefs", () => {
  it("round-trips", () => {
    const s = memoryStorage();
    savePrefs(MINE, s);
    expect(loadPrefs(s)).toEqual(MINE);
  });

  it("defaults when nothing is stored", () => {
    expect(loadPrefs(memoryStorage())).toEqual(DEFAULT_PREFS);
  });

  it("defaults when storage throws, and saving doesn't throw", () => {
    expect(loadPrefs(throwingStorage())).toEqual(DEFAULT_PREFS);
    expect(() => savePrefs(MINE, throwingStorage())).not.toThrow();
  });

  it("defaults on corrupt or wrong-shaped JSON", () => {
    const s = memoryStorage();
    s.setItem("matchmind.prefs", "{not json");
    expect(loadPrefs(s)).toEqual(DEFAULT_PREFS);
    s.setItem("matchmind.prefs", JSON.stringify({ mode: "pundit", lang: "de" }));
    expect(loadPrefs(s)).toEqual(DEFAULT_PREFS);
  });

  it("is a fresh object each time (no shared mutation)", () => {
    const a = loadPrefs(memoryStorage());
    a.sides["x"] = "y";
    expect(loadPrefs(memoryStorage()).sides).toEqual({});
  });
});
