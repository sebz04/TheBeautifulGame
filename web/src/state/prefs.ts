// The fan's choices, kept in the browser. Storage can throw (private mode, blocked site
// data), so every access is guarded and a bad value falls back to the defaults.
import type { Lang } from "../api/types";

export type Mode = "fan" | "scout";
export type Focus = "team" | "player";

export interface Prefs {
  mode: Mode;
  focus: Focus;
  lang: Lang;
  favorite_club_id: string | null;
  favorite_player_id: string | null;
  /** The side a fan picked for a match their club isn't in: match_id → club_id. */
  sides: Record<string, string>;
}

const KEY = "matchmind.prefs";
const LANGS: readonly Lang[] = ["en", "es", "pt", "fr", "ar"];

export const DEFAULT_PREFS: Readonly<Prefs> = Object.freeze({
  mode: "fan",
  focus: "team",
  lang: "en",
  favorite_club_id: null,
  favorite_player_id: null,
  sides: {},
});

function defaults(): Prefs {
  return { ...DEFAULT_PREFS, sides: {} };
}

function valid(p: Partial<Prefs>): p is Prefs {
  const idOrNull = (v: unknown) => v === null || typeof v === "string";
  return (
    (p.mode === "fan" || p.mode === "scout") &&
    (p.focus === "team" || p.focus === "player") &&
    LANGS.includes(p.lang as Lang) &&
    idOrNull(p.favorite_club_id) &&
    idOrNull(p.favorite_player_id) &&
    typeof p.sides === "object" &&
    p.sides !== null &&
    Object.values(p.sides).every((v) => typeof v === "string")
  );
}

function storage(): Storage | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

export function loadPrefs(store: Storage | undefined = storage()): Prefs {
  try {
    const raw = store?.getItem(KEY);
    if (!raw) return defaults();
    const parsed = JSON.parse(raw) as Partial<Prefs>;
    return valid(parsed) ? { ...parsed, sides: { ...parsed.sides } } : defaults();
  } catch {
    return defaults();
  }
}

/** Has the visitor finished the welcome page before? */
export function hasSavedPrefs(store: Storage | undefined = storage()): boolean {
  try {
    return Boolean(store?.getItem(KEY));
  } catch {
    return false;
  }
}

export function savePrefs(p: Prefs, store: Storage | undefined = storage()): void {
  try {
    store?.setItem(KEY, JSON.stringify(p));
  } catch {
    // Not saved: the app still works for this visit.
  }
}
