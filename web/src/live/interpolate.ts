// Smooth motion from 5 Hz frames: positions in between two frames, and one continuous
// match clock across half time.
import type { Frame, Period } from "../api/types";

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

/** The frame at time ``t`` between ``a`` and ``b`` (same period), clamped to them. A player
 * in only one of the two frames is drawn where that frame has them. */
export function interpolate(a: Frame, b: Frame, t: number): Frame {
  const span = b.t - a.t;
  const k = span > 0 ? Math.min(1, Math.max(0, (t - a.t) / span)) : 1;
  const next = new Map(b.players.map((p) => [p.player_id, p]));
  const players = a.players.map((p) => {
    const q = next.get(p.player_id);
    return q ? { ...p, x: lerp(p.x, q.x, k), y: lerp(p.y, q.y, k) } : p;
  });
  const known = new Set(a.players.map((p) => p.player_id));
  for (const q of b.players) if (!known.has(q.player_id)) players.push(q); // a substitute coming on
  const ball = a.ball.map((v, i) => lerp(v, b.ball[i], k)) as Frame["ball"];
  return { ...a, t: lerp(a.t, b.t, k), ball, players };
}

/** Seconds since kickoff, counting first-half added time (``firstHalfS`` is its length). */
export function clockOf(period: Period, t: number, firstHalfS: number): number {
  return period === 1 ? t : firstHalfS + t;
}

export function fromClock(clock: number, firstHalfS: number): { period: Period; t: number } {
  return clock < firstHalfS ? { period: 1, t: clock } : { period: 2, t: clock - firstHalfS };
}

/** "39:12" style label for a period and t. */
export function clockLabel(t: number): string {
  const s = Math.max(0, Math.floor(t));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
