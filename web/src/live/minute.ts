// The minute a fan reads: "63'", or "45+2'" in added time (as the agents write it).
import type { Period } from "../api/types";

export function minuteLabel(period: Period, t: number, addedS: [number, number]): string {
  const base = period === 1 ? 0 : 45;
  const into = Math.floor(t / 60) + 1;
  if (into > 45 && t <= 45 * 60 + addedS[period - 1]) return `${base + 45}+${into - 45}'`;
  return `${base + Math.min(into, 45)}'`;
}
