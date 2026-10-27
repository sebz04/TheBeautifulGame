import type { KeyboardEvent } from "react";

import type { Period } from "../api/types";
import { clockLabel, clockOf, fromClock } from "../live/interpolate";
import { useT } from "../i18n/i18n";
import { SPEEDS, type Speed } from "../state/store";

export interface PlaybackBarProps {
  playing: boolean;
  speed: Speed;
  period: Period;
  t: number;
  firstHalfS: number;
  secondHalfS: number;
  onToggle: () => void;
  onSpeed: (s: Speed) => void;
  onSeek: (period: Period, t: number) => void;
}

export default function PlaybackBar(p: PlaybackBarProps) {
  const t = useT();
  const total = p.firstHalfS + p.secondHalfS;
  const half = t(p.period === 1 ? "play.first" : "play.second", { clock: clockLabel(p.t) });
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const tag = (e.target as HTMLElement).tagName;
    if (e.key === " " && tag !== "BUTTON" && tag !== "INPUT") {
      e.preventDefault();
      p.onToggle();
    }
  };
  return (
    <div role="group" aria-label={t("play.group")} tabIndex={-1} onKeyDown={onKey} className="mt-3 flex flex-wrap items-center gap-3 text-sm text-muted">
      <button
        type="button"
        aria-label={p.playing ? t("play.pause") : t("play.play")}
        onClick={p.onToggle}
        className="grid h-10 w-10 place-items-center rounded-full border-0 bg-accent text-on-accent"
      >
        <span aria-hidden="true">{p.playing ? "❚❚" : "▶"}</span>
      </button>
      <div role="group" aria-label={t("play.speed")} className="flex gap-1">
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={p.speed === s}
            dir="ltr"
            onClick={() => p.onSpeed(s)}
            className={`border bg-transparent px-2 py-1 text-xs ${p.speed === s ? "border-text text-text" : "border-[color:var(--mm-rule)] text-muted"}`}
          >
            {s}×
          </button>
        ))}
      </div>
      <input
        type="range"
        dir="ltr"
        aria-label={t("play.time")}
        min={0}
        max={Math.round(total)}
        step={1}
        value={Math.round(clockOf(p.period, p.t, p.firstHalfS))}
        aria-valuetext={half}
        onChange={(e) => {
          const { period, t } = fromClock(Number(e.target.value), p.firstHalfS);
          p.onSeek(period, t);
        }}
        className="min-w-[8rem] flex-1 accent-[color:var(--mm-accent)]"
      />
      <span>{half}</span>
    </div>
  );
}
