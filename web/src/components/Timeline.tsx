// Key moments along the match; a marker jumps the replay to that moment.
import type { Moment, Period } from "../api/types";
import { clockOf } from "../live/interpolate";
import { minuteLabel } from "../live/minute";

const KIND_COLOR: Record<string, string> = {
  goal: "var(--mm-accent)",
  red_card: "var(--mm-warn)",
};

const KIND_NAMES: Record<string, string> = {
  player_deviation: "Player stands out",
  pressing_collapse: "Press drops off",
  formation_shift: "Change of shape",
  momentum_swing: "Momentum swing",
  corner_pressure: "Corner pressure",
};

/** A moment kind in plain words ("player_deviation" → "Player stands out"). */
export function kindLabel(kind: string): string {
  const words = KIND_NAMES[kind] ?? kind.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export interface TimelineProps {
  moments: Moment[];
  firstHalfS: number;
  totalS: number;
  period: Period;
  t: number;
  addedS: [number, number];
  onSeek: (period: Period, t: number) => void;
}

export default function Timeline({ moments, firstHalfS, totalS, period, t, addedS, onSeek }: TimelineProps) {
  const pct = (p: Period, s: number) => `${(clockOf(p, s, firstHalfS) / totalS) * 100}%`;
  return (
    <div dir="ltr" className="relative h-9" aria-label="Key moments">
      <div className="absolute left-0 right-0 top-1/2 h-px bg-[color:var(--mm-rule)]" />
      <div className="absolute bottom-0 top-0 w-px bg-[color:var(--mm-muted)]" style={{ left: pct(1, firstHalfS) }} aria-hidden="true" />
      <div className="absolute bottom-0 top-0 w-0.5 bg-accent" style={{ left: pct(period, t) }} aria-hidden="true" />
      {moments.map((m) => (
        <button
          key={m.moment_id}
          type="button"
          aria-label={`${kindLabel(m.kind)}, ${minuteLabel(m.period, m.t_start, addedS)}`}
          title={`${kindLabel(m.kind)}, ${minuteLabel(m.period, m.t_start, addedS)}`}
          onClick={() => onSeek(m.period, m.t_start)}
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface p-0"
          style={{ left: pct(m.period, m.t_start), background: KIND_COLOR[m.kind] ?? "var(--mm-muted)" }}
        />
      ))}
    </div>
  );
}
