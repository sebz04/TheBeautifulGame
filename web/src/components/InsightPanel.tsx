// The pundit's column: the newest insight up to the replay's time, big, with the earlier
// ones listed by minute underneath (click one to bring it back to the top).
import { useState } from "react";

import type { InsightRow, Moment, Period } from "../api/types";
import { minuteLabel } from "../live/minute";
import InsightCard from "./InsightCard";

const EARLIER = 6;

/** Rows whose moment has ended by (period, t), newest first. */
export function insightsSoFar(rows: InsightRow[], moments: Record<string, Moment>, period: Period, t: number): InsightRow[] {
  const end = (r: InsightRow) => moments[r.insight.moment_id];
  return rows
    .filter((r) => {
      const m = end(r);
      return m && (m.period < period || (m.period === period && m.t_end <= t));
    })
    .sort((a, b) => {
      const [ma, mb] = [end(a), end(b)];
      return mb.period - ma.period || mb.t_end - ma.t_end;
    });
}

export interface InsightPanelProps {
  rows: InsightRow[];
  moments: Record<string, Moment>;
  period: Period;
  t: number;
  addedS: [number, number];
  onAskWhy: (row: InsightRow) => void;
  onBestPlay: (row: InsightRow, eventId: string) => void;
}

export default function InsightPanel({ rows, moments, period, t, addedS, onAskWhy, onBestPlay }: InsightPanelProps) {
  const [pinned, setPinned] = useState<string | null>(null);
  const soFar = insightsSoFar(rows, moments, period, t);
  if (soFar.length === 0) {
    return (
      <div className="bg-surface p-6 text-text">
        <p className="m-0 font-display text-3xl font-extrabold">Your pundit is watching.</p>
        <p className="mb-0 mt-2 text-sm text-muted">The first insight appears at the first key moment. Press play, or jump to a moment on the timeline.</p>
      </div>
    );
  }
  const top = soFar.find((r) => r.insight.insight_id === pinned) ?? soFar[0];
  const minuteOf = (r: InsightRow) => {
    const m = moments[r.insight.moment_id];
    return minuteLabel(m.period, m.t_end, addedS);
  };
  return (
    <div>
      <InsightCard key={top.insight.insight_id} row={top} minute={minuteOf(top)} onAskWhy={() => onAskWhy(top)} onBestPlay={(e) => onBestPlay(top, e)} />
      {soFar.length > 1 && (
        <ul className="m-0 mt-0.5 list-none bg-surface px-6 py-1.5 text-text" aria-label="Earlier insights">
          {soFar
            .filter((r) => r !== top)
            .slice(0, EARLIER)
            .map((r) => (
              <li key={r.insight.insight_id} className="border-t border-[color:var(--mm-rule)] first:border-t-0">
                <button
                  type="button"
                  onClick={() => setPinned(r.insight.insight_id)}
                  lang={r.text.lang}
                  dir={r.text.dir}
                  className="grid w-full grid-cols-[3.2rem_1fr] gap-2.5 border-0 bg-transparent py-3 text-start text-sm text-text"
                >
                  <span className="font-display text-xl font-extrabold text-muted">{minuteOf(r)}</span>
                  <span>{r.text.headline}</span>
                </button>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
