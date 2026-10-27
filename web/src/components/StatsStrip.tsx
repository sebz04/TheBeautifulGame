// A few key numbers for both teams at the replay's time, refreshed every 5 s of match time.
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Period, Stats } from "../api/types";
import { useT, type Key } from "../i18n/i18n";

const STEP_S = 5;

const ROWS: { key: string; label: Key; show: (v: number) => string }[] = [
  { key: "xg", label: "stat.xg", show: (v) => v.toFixed(2) },
  { key: "possession", label: "stat.possession", show: (v) => `${Math.round(v * 100)}%` },
  { key: "shots", label: "stat.shots", show: (v) => String(Math.round(v)) },
  { key: "shots_on_target", label: "stat.shots_on_target", show: (v) => String(Math.round(v)) },
  { key: "ppda", label: "stat.ppda", show: (v) => v.toFixed(1) },
];

export default function StatsStrip({ matchId, homeId, awayId, period, t }: { matchId: string; homeId: string; awayId: string; period: Period; t: number }) {
  const t_ = useT();
  const [stats, setStats] = useState<[Stats, Stats] | null>(null);
  const step = Math.floor(t / STEP_S); // refetch whenever the match clock crosses a step (seeks too)

  useEffect(() => {
    let live = true;
    Promise.all([homeId, awayId].map((id) => api.stats(matchId, { scope: "team", scope_id: id, period, t: step * STEP_S })))
      .then(([h, a]) => live && setStats([h, a]))
      .catch(() => undefined); // keep the last numbers; the next step tries again
    return () => {
      live = false;
    };
  }, [matchId, homeId, awayId, period, step]);

  return (
    <section aria-label={t_("stats.label")} className="grid grid-cols-2 bg-surface text-text md:grid-cols-5">
      {ROWS.map((r, i) => {
        const [h, a] = stats ? stats.map((s) => s.metrics[r.key]) : [null, null];
        return (
          <div key={r.key} className={`px-4 py-3.5 ${i ? "border-l border-[color:var(--mm-rule)]" : ""}`}>
            <div className="text-xs text-muted">{t_(r.label)}</div>
            <div className="mt-1 flex items-baseline justify-between font-display text-3xl font-extrabold tabular-nums">
              <span>{h == null ? "–" : r.show(h)}</span>
              <span style={{ color: "var(--mm-away-text, var(--mm-text))" }}>{a == null ? "–" : r.show(a)}</span>
            </div>
          </div>
        );
      })}
    </section>
  );
}
