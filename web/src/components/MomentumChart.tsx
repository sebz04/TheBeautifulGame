// Momentum through the match: above the line the home side is on top, below it the away
// side. Drawn with visx; a playhead marks the replay's time.
import { curveMonotoneX } from "@visx/curve";
import { scaleLinear } from "@visx/scale";
import { AreaClosed } from "@visx/shape";

import type { MomentumPoint, Period } from "../api/types";
import { clockOf } from "../live/interpolate";

const W = 1000;
const H = 96;

export interface MomentumChartProps {
  points: MomentumPoint[];
  firstHalfS: number;
  totalS: number;
  period: Period;
  t: number;
  homeName: string;
  awayName: string;
}

export default function MomentumChart({ points, firstHalfS, totalS, period, t, homeName, awayName }: MomentumChartProps) {
  const peak = Math.max(0.05, ...points.map((p) => Math.abs(p.diff)));
  const x = scaleLinear({ domain: [0, totalS], range: [0, W] });
  const y = scaleLinear({ domain: [-peak, peak], range: [H - 4, 4] });
  const at = (p: MomentumPoint) => x(clockOf(p.period, p.t, firstHalfS));
  const home = points.map((p) => ({ ...p, diff: Math.max(0, p.diff) }));
  const away = points.map((p) => ({ ...p, diff: Math.min(0, p.diff) }));
  return (
    <figure dir="ltr" className="m-0">
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={`Momentum: above the line ${homeName} on top, below ${awayName}`}>
        <line x1={0} x2={W} y1={y(0)} y2={y(0)} stroke="var(--mm-rule)" />
        <AreaClosed data={home} x={at} y={(p) => y(p.diff)} yScale={y} y0={() => y(0)} curve={curveMonotoneX} fill="var(--mm-home)" stroke="var(--mm-text)" strokeOpacity={0.35} />
        <AreaClosed data={away} x={at} y={(p) => y(p.diff)} yScale={y} y0={() => y(0)} curve={curveMonotoneX} fill="var(--mm-away)" />
        <line x1={x(clockOf(period, t, firstHalfS))} x2={x(clockOf(period, t, firstHalfS))} y1={0} y2={H} stroke="var(--mm-accent)" strokeWidth={2} />
      </svg>
      <figcaption className="mt-1.5 flex gap-4 text-xs text-muted">
        <span><i className="mr-1.5 inline-block h-2.5 w-2.5 align-[-1px]" style={{ background: "var(--mm-home)" }} />{homeName} on top</span>
        <span><i className="mr-1.5 inline-block h-2.5 w-2.5 align-[-1px]" style={{ background: "var(--mm-away)" }} />{awayName} on top</span>
      </figcaption>
    </figure>
  );
}
