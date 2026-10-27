import type { KeyboardEvent } from "react";

import type { Period } from "../api/types";
import { clockLabel, clockOf, fromClock } from "../live/interpolate";
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
  const total = p.firstHalfS + p.secondHalfS;
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const tag = (e.target as HTMLElement).tagName;
    if (e.key === " " && tag !== "BUTTON" && tag !== "INPUT") {
      e.preventDefault();
      p.onToggle();
    }
  };
  return (
    <div role="group" aria-label="Playback" tabIndex={-1} onKeyDown={onKey} className="mt-3 flex flex-wrap items-center gap-3 text-sm text-muted">
      <button
        type="button"
        aria-label={p.playing ? "Pause" : "Play"}
        onClick={p.onToggle}
        className="grid h-10 w-10 place-items-center rounded-full border-0 bg-accent text-on-accent"
      >
        <span aria-hidden="true">{p.playing ? "❚❚" : "▶"}</span>
      </button>
      <div role="group" aria-label="Speed" className="flex gap-1">
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={p.speed === s}
            onClick={() => p.onSpeed(s)}
            className={`border bg-transparent px-2 py-1 text-xs ${p.speed === s ? "border-text text-text" : "border-[color:var(--mm-rule)] text-muted"}`}
          >
            {s}×
          </button>
        ))}
      </div>
      <input
        type="range"
        aria-label="Match time"
        min={0}
        max={Math.round(total)}
        step={1}
        value={Math.round(clockOf(p.period, p.t, p.firstHalfS))}
        aria-valuetext={`${p.period === 1 ? "First" : "Second"} half, ${clockLabel(p.t)}`}
        onChange={(e) => {
          const { period, t } = fromClock(Number(e.target.value), p.firstHalfS);
          p.onSeek(period, t);
        }}
        className="min-w-[8rem] flex-1 accent-[color:var(--mm-accent)]"
      />
      <span>
        {p.period === 1 ? "First" : "Second"} half, {clockLabel(p.t)}
      </span>
    </div>
  );
}
