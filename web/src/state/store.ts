// App state: the fan's preferences (persisted) and the replay's playback position.
import { create } from "zustand";

import type { Period } from "../api/types";
import { loadPrefs, savePrefs, type Prefs } from "./prefs";

export const SPEEDS = [0.5, 1, 2, 4, 8] as const;
export type Speed = (typeof SPEEDS)[number];

export interface AppState {
  prefs: Prefs;
  setPrefs: (patch: Partial<Prefs>) => void;
  period: Period;
  t: number;
  playing: boolean;
  speed: Speed;
  setClock: (period: Period, t: number) => void;
  setPlaying: (playing: boolean) => void;
  setSpeedValue: (speed: Speed) => void;
}

export const useStore = create<AppState>((set) => ({
  prefs: loadPrefs(),
  setPrefs: (patch) =>
    set((s) => {
      const prefs = { ...s.prefs, ...patch };
      savePrefs(prefs);
      return { prefs };
    }),
  period: 1,
  t: 0,
  playing: false,
  speed: 1,
  setClock: (period, t) => set({ period, t }),
  setPlaying: (playing) => set({ playing }),
  setSpeedValue: (speed) => set({ speed }),
}));
