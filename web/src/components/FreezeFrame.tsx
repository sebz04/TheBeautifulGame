// The decision, frozen: everyone where they were, the space each side controlled, the real
// choice dashed, the best option as an arrow, and a scorecard comparing them. Other options
// are one tap away. 10 SVG units per metre; the pitch never mirrors.
import { useState } from "react";

import type { Counterfactual, Frame, Option, PitchControl } from "../api/types";
import { useT } from "../i18n/i18n";
import { dangerText, optionWhat } from "../lib/options";

const S = 10;
const MAX_OTHERS = 5;

export interface FreezeFrameProps {
  cf: Counterfactual;
  from: [number, number];
  frame: Frame | null;
  heat: PitchControl | null;
  colors: { home: string; away: string; homeId: string };
  names: Record<string, string>;
}

const px = ([x, y]: [number, number]) => [x * S, (68 - y) * S] as const;

function Heat({ heat, color }: { heat: PitchControl; color: string }) {
  const rows = heat.grid.length;
  const cols = heat.grid[0]?.length ?? 0;
  const w = (105 * S) / cols;
  const h = (68 * S) / rows;
  return (
    <g style={{ filter: "blur(18px)" }} aria-hidden="true">
      {heat.grid.flatMap((row, r) =>
        row.map((v, c) => <rect key={`${r}-${c}`} x={c * w} y={(rows - 1 - r) * h} width={w + 1} height={h + 1} fill={color} opacity={0.5 * v} />),
      )}
    </g>
  );
}

export default function FreezeFrame({ cf, from, frame, heat, colors, names }: FreezeFrameProps) {
  const t = useT();
  const [picked, setPicked] = useState<number | null>(null);
  const others = cf.alternatives.slice(1, 1 + MAX_OTHERS);
  const [ox, oy] = px(from);
  const line = (o: Option) => px(o.end);
  const [cx, cy] = line(cf.chosen);
  const [bx, by] = line(cf.best);
  const alt = picked === null ? null : others[picked];
  const same = cf.chosen.kind === cf.best.kind && cf.chosen.end[0] === cf.best.end[0] && cf.chosen.end[1] === cf.best.end[1];

  const card = (label: string, o: Option, strong: boolean) => (
    <div role="group" aria-label={label} className={`flex-1 p-3 text-sm ${strong ? "bg-accent text-on-accent" : "border-2 border-dashed border-[color:var(--mm-muted)]"}`}>
      <b className="block">{label}</b>
      <span className="block">{optionWhat(o, names, t)}</span>
      <span className="block font-display text-2xl font-extrabold">{Math.round(o.pc_prob * 100)}%</span>
      <span className="block text-xs">{t("best.chance", { chance: Math.round(o.pc_prob * 100) })}, {dangerText(o, t)}</span>
    </div>
  );

  return (
    <div>
      <svg viewBox={`0 0 ${105 * S} ${68 * S}`} role="img" aria-label={t("why.pitch")} className="block h-auto w-full bg-[color:var(--mm-pitch)]">
        <defs>
          <marker id="ff-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill="var(--mm-accent)" />
          </marker>
        </defs>
        {heat && <Heat heat={heat} color={heat.attacking_team === colors.homeId ? colors.home : colors.away} />}
        <g fill="none" stroke="var(--mm-pitch-line)" strokeWidth="3">
          <rect x="2" y="2" width={105 * S - 4} height={68 * S - 4} />
          <line x1={52.5 * S} y1="0" x2={52.5 * S} y2={68 * S} />
          <circle cx={52.5 * S} cy={34 * S} r={9.15 * S} />
          <rect x="2" y={13.85 * S} width={16.5 * S} height={40.3 * S} />
          <rect x={88.5 * S} y={13.85 * S} width={16.5 * S - 2} height={40.3 * S} />
        </g>
        {frame?.players.map((p) => (
          <circle key={p.player_id} cx={p.x * S} cy={(68 - p.y) * S} r={11} fill={p.team_id === colors.homeId ? colors.home : colors.away} stroke="#fff" strokeWidth="3" />
        ))}
        {!same && <line data-line="real" x1={ox} y1={oy} x2={cx} y2={cy} stroke="var(--mm-muted)" strokeWidth="6" strokeDasharray="14 10" />}
        <line data-line="best" x1={ox} y1={oy} x2={bx} y2={by} stroke="var(--mm-accent)" strokeWidth="8" markerEnd="url(#ff-arrow)" />
        {alt && <line data-line="picked" x1={ox} y1={oy} x2={alt.end[0] * S} y2={(68 - alt.end[1]) * S} stroke="var(--mm-text)" strokeWidth="5" strokeDasharray="4 8" />}
        <circle cx={ox} cy={oy} r={14} fill={colors.home} stroke="#fff" strokeWidth="4" />
      </svg>

      {same ? (
        <div className="mt-3">
          <p className="m-0 mb-2 font-display text-2xl font-extrabold">{t("best.sameAsBest")}</p>
          {card(t("best.bestPlay"), cf.best, true)}
        </div>
      ) : (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          {card(t("best.real"), cf.chosen, false)}
          {card(t("best.bestPlay"), cf.best, true)}
        </div>
      )}

      {others.length > 0 && (
        <div role="group" aria-label={t("best.others")} className="mt-3 flex flex-wrap gap-2">
          <span className="w-full text-xs text-muted">{t("best.others")}</span>
          {others.map((o, i) => (
            <button
              key={`${o.kind}-${o.end.join(",")}`}
              type="button"
              aria-pressed={picked === i}
              onClick={() => setPicked(picked === i ? null : i)}
              className={`border px-3 py-2 text-sm ${picked === i ? "border-text bg-text text-surface" : "border-[color:var(--mm-rule)] bg-transparent text-text"}`}
            >
              {optionWhat(o, names, t)}, {Math.round(o.pc_prob * 100)}%
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
