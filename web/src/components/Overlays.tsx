// The fast lane: precomputed cues (name tags, speed and distance alerts) shown at their
// time, at most three at once so the pitch stays readable.
import type { Cue, Period } from "../api/types";
import { useT } from "../i18n/i18n";

export const MAX_CUES = 3;

export function visibleCues(cues: Cue[], period: Period, t: number, max = MAX_CUES): Cue[] {
  return cues
    .filter((c) => c.period === period && c.t_in <= t && t < c.t_out)
    .sort((a, b) => b.priority - a.priority || b.t_in - a.t_in)
    .slice(0, max);
}

function text(c: Cue, names: Record<string, string>, ran: (who: string, km: string) => string): string {
  const who = names[String(c.payload.player_id ?? "")] ?? "A player";
  if (c.kind === "speed_alert") return `${who}, ${(Number(c.payload.speed_ms) * 3.6).toFixed(1)} km/h`;
  if (c.kind === "distance_alert") return ran(who, (Number(c.payload.distance_m) / 1000).toFixed(1));
  return who;
}

export interface OverlaysProps {
  cues: Cue[];
  period: Period;
  t: number;
  names: Record<string, string>;
  /** Where each player is now, in metres (105 × 68), to pin tags to them. */
  positions?: Record<string, { x: number; y: number }>;
}

export default function Overlays({ cues, period, t, names, positions = {} }: OverlaysProps) {
  const tr = useT();
  const ran = (who: string, km: string) => tr("overlay.ran", { who, km });
  const shown = visibleCues(cues, period, t);
  let corner = 0;
  return (
    <div className="pointer-events-none absolute inset-0" aria-live="polite">
      {shown.map((c) => {
        const at = positions[String(c.payload.player_id ?? "")];
        const pinned = at && c.kind !== "distance_alert";
        const style = pinned
          ? { left: `${(at.x / 105) * 100}%`, top: `${((68 - at.y) / 68) * 100}%`, transform: "translate(-50%, -150%)" }
          : { left: "8px", top: `${8 + 34 * corner++}px` };
        return (
          <div
            key={c.cue_id}
            role="note"
            style={style}
            className="absolute whitespace-nowrap bg-accent px-2 py-1 text-xs font-bold text-on-accent shadow"
          >
            {text(c, names, ran)}
          </div>
        );
      })}
    </div>
  );
}
