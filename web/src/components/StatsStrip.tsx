// A few key numbers for both teams at the replay's time, refreshed every few seconds.
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { Period, Stats } from "../api/types";

const EVERY_MS = 5000;

const ROWS: { key: string; label: string; show: (v: number) => string }[] = [
  { key: "xg", label: "Expected goals", show: (v) => v.toFixed(2) },
  { key: "possession", label: "Possession", show: (v) => `${Math.round(v * 100)}%` },
  { key: "shots", label: "Shots", show: (v) => String(Math.round(v)) },
  { key: "shots_on_target", label: "On target", show: (v) => String(Math.round(v)) },
  { key: "ppda", label: "Passes per defensive action", show: (v) => v.toFixed(1) },
];

export default function StatsStrip({ matchId, homeId, awayId, period, t }: { matchId: string; homeId: string; awayId: string; period: Period; t: number }) {
  const [stats, setStats] = useState<[Stats, Stats] | null>(null);
  const last = useRef(0);
  const clock = useRef({ period, t });
  clock.current = { period, t };

  useEffect(() => {
    let live = true;
    const load = () => {
      last.current = Date.now();
      const { period: p, t: now } = clock.current;
      Promise.all([homeId, awayId].map((id) => api.stats(matchId, { scope: "team", scope_id: id, period: p, t: Math.floor(now) })))
        .then(([h, a]) => live && setStats([h, a]))
        .catch(() => undefined); // keep the last numbers; the next tick tries again
    };
    load();
    const timer = setInterval(() => Date.now() - last.current >= EVERY_MS && load(), 1000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [matchId, homeId, awayId]);

  return (
    <section aria-label="Key stats, home then away" className="grid grid-cols-2 bg-surface text-text md:grid-cols-5">
      {ROWS.map((r, i) => {
        const [h, a] = stats ? stats.map((s) => s.metrics[r.key]) : [null, null];
        return (
          <div key={r.key} className={`px-4 py-3.5 ${i ? "border-l border-[color:var(--mm-rule)]" : ""}`}>
            <div className="text-xs text-muted">{r.label}</div>
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
