// When the fan's club isn't playing: pick a side for this match (remembered per match).
import { useEffect, useRef } from "react";

import type { Club } from "../api/types";
import { textOn } from "../design/theme";
import { useT } from "../i18n/i18n";

export default function SidePicker({ home, away, onPick }: { home: Club; away: Club; onPick: (clubId: string) => void }) {
  const t = useT();
  const first = useRef<HTMLButtonElement>(null);
  useEffect(() => first.current?.focus(), []);
  return (
    <div className="fixed inset-0 z-20 grid place-items-center bg-black/70 p-4">
      <section role="dialog" aria-modal="true" aria-labelledby="side-title" className="w-full max-w-lg bg-surface p-6 text-text">
        <h2 id="side-title" className="m-0 font-display text-4xl font-black">
          {t("side.title")}
        </h2>
        <p className="text-muted">{t("side.prompt")}</p>
        <div className="mt-4 grid grid-cols-2 gap-3">
          {[home, away].map((c, i) => (
            <button
              key={c.club_id}
              ref={i === 0 ? first : undefined}
              type="button"
              onClick={() => onPick(c.club_id)}
              className="flex min-h-24 flex-col justify-end border-0 p-4 text-left font-bold"
              style={{ background: c.primary_color, color: textOn(c.primary_color) }}
            >
              <span className="font-display text-3xl font-black" style={{ color: "inherit" }}>
                {c.short}
              </span>
              <span>{c.name}</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
