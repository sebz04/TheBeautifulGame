// App state: the fan's preferences (persisted) and the live replay. The stream lives here,
// not in a page, so it keeps playing when the viewer switches to the Best Plays tab.
import { create } from "zustand";

import type { Cue, Frame, LiveInsight, MatchEvent, Period } from "../api/types";
import { openLive, type LiveHandle, type LiveStatus } from "../live/stream";
import { loadPrefs, savePrefs, type Prefs } from "./prefs";

export const SPEEDS = [0.5, 1, 2, 4, 8] as const;
export type Speed = (typeof SPEEDS)[number];

const FRAME_BUFFER = 12; // about 2.4 s of 5 Hz frames, enough to interpolate behind the newest
const RECENT_EVENTS = 30;

export interface ArrivedFrame extends Frame {
  arrived: number; // performance.now() when it came in
}

export interface AppState {
  prefs: Prefs;
  setPrefs: (patch: Partial<Prefs>) => void;

  matchId: string | null;
  period: Period;
  t: number;
  playing: boolean;
  speed: Speed;
  connection: LiveStatus | "idle";
  ended: boolean;
  frames: ArrivedFrame[];
  cues: Cue[];
  events: MatchEvent[];
  liveInsights: LiveInsight[];

  setClock: (period: Period, t: number) => void;
  setPlaying: (playing: boolean) => void;
  setSpeedValue: (speed: Speed) => void;
  /** Point the replay at a match, paused at kickoff (or keep it if it's already this one). */
  openMatch: (matchId: string) => void;
  play: () => void;
  pause: () => void;
  seek: (period: Period, t: number) => void;
  setSpeed: (speed: Speed) => void;
}

let handle: LiveHandle | null = null;
let seenInsights = new Set<string>();

export const useStore = create<AppState>((set, get) => {
  const stop = () => {
    handle?.close();
    handle = null;
  };

  const start = () => {
    const { matchId, period, t, speed } = get();
    if (!matchId) return;
    stop();
    set({ frames: [], playing: true, ended: false });
    handle = openLive(
      matchId,
      { period, from_t: Math.round(t * 10) / 10, speed },
      {
        frame: (f) =>
          set((s) => ({
            frames: [...s.frames.slice(-(FRAME_BUFFER - 1)), { ...f, arrived: performance.now() }],
            period: f.period,
            t: f.t,
          })),
        event: (e) => set((s) => ({ events: [...s.events.slice(-(RECENT_EVENTS - 1)), e] })),
        cue: (c) => set((s) => ({ cues: [...s.cues.filter((x) => x.t_out > c.t_in - 1 || x.period !== c.period), c] })),
        insight: (i) => set((s) => ({ liveInsights: [...s.liveInsights, i] })),
        end: () => set({ playing: false, ended: true }),
        status: (connection) => set({ connection }),
      },
      seenInsights,
    );
  };

  return {
    prefs: loadPrefs(),
    setPrefs: (patch) =>
      set((s) => {
        const prefs = { ...s.prefs, ...patch };
        savePrefs(prefs);
        return { prefs };
      }),

    matchId: null,
    period: 1,
    t: 0,
    playing: false,
    speed: 1,
    connection: "idle",
    ended: false,
    frames: [],
    cues: [],
    events: [],
    liveInsights: [],

    setClock: (period, t) => set({ period, t }),
    setPlaying: (playing) => set({ playing }),
    setSpeedValue: (speed) => set({ speed }),

    openMatch: (matchId) => {
      if (get().matchId === matchId) return;
      stop();
      seenInsights = new Set();
      set({ matchId, period: 1, t: 0, playing: false, ended: false, connection: "idle",
            frames: [], cues: [], events: [], liveInsights: [] }); // prettier-ignore
    },
    play: () => {
      if (get().ended) set({ period: 1, t: 0 });
      start();
    },
    pause: () => {
      stop();
      set({ playing: false });
    },
    seek: (period, t) => {
      set({ period, t, cues: [], ended: false });
      if (get().playing) start();
    },
    setSpeed: (speed) => {
      set({ speed });
      if (get().playing) start();
    },
  };
});
