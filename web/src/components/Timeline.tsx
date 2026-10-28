// Key moments along the match; a marker jumps the replay to that moment.
import type { Moment, Period } from "../api/types";
import { clockOf } from "../live/interpolate";
import { translate, useT } from "../i18n/i18n";
import { minuteLabel } from "../live/minute";
import type { Lang } from "../api/types";
import { useStore } from "../state/store";

const KIND_COLOR: Record<string, string> = {
  goal: "var(--mm-accent)",
  red_card: "var(--mm-warn)",
};

/** A moment kind in plain words ("player_deviation" → "Player stands out"). */
export function kindLabel(kind: string, lang: Lang = "en"): string {
  const key = `kind.${kind}`;
  const words = translate(lang, key);
  if (words !== key) return words;
  const plain = kind.replace(/_/g, " ");
  return plain.charAt(0).toUpperCase() + plain.slice(1);
}

const LEAD_IN_S = 5;
const LONG_S = 20;

/** Where a marker jumps to: 5 s before the moment, so the viewer sees it happen and the
 * pundit's card arrives as it ends. A long moment (a momentum swing over minutes) starts 5 s
 * before its end instead, where the insight lands. */
export function leadIn(m: Moment): number {
  const from = m.t_end - m.t_start > LONG_S ? m.t_end : m.t_start;
  return Math.max(0, from - LEAD_IN_S);
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
  const tr = useT();
  const lang = useStore((s) => s.prefs.lang);
  const pct = (p: Period, s: number) => `${(clockOf(p, s, firstHalfS) / totalS) * 100}%`;
  return (
    <div dir="ltr" className="relative h-9" aria-label={tr("match.moments")}>
      <div className="absolute left-0 right-0 top-1/2 h-px bg-[color:var(--mm-rule)]" />
      <div className="absolute bottom-0 top-0 w-px bg-[color:var(--mm-muted)]" style={{ left: pct(1, firstHalfS) }} aria-hidden="true" />
      <div className="absolute bottom-0 top-0 w-0.5 bg-accent" style={{ left: pct(period, t) }} aria-hidden="true" />
      {moments.map((m) => (
        <button
          key={m.moment_id}
          type="button"
          aria-label={`${kindLabel(m.kind, lang)}, ${minuteLabel(m.period, m.t_start, addedS)}`}
          title={`${kindLabel(m.kind, lang)}, ${minuteLabel(m.period, m.t_start, addedS)}`}
          onClick={() => onSeek(m.period, leadIn(m))}
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface p-0"
          style={{ left: pct(m.period, m.t_start), background: KIND_COLOR[m.kind] ?? "var(--mm-muted)" }}
        />
      ))}
    </div>
  );
}
