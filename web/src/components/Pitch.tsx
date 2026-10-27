// The live pitch: a canvas redrawn every animation frame. It renders slightly behind the
// newest 5 Hz frame and interpolates, so motion is smooth at 60 fps. The pitch is physical
// space, so it never mirrors for right-to-left languages.
import { useEffect, useRef } from "react";

import type { Frame } from "../api/types";
import { interpolate } from "../live/interpolate";
import { useStore, type ArrivedFrame } from "../state/store";

const LENGTH = 105;
const WIDTH = 68;
const DELAY_S = 0.2; // render one frame interval behind the newest

export interface PitchColors {
  home: string; // team_id → fill
  away: string;
  homeId: string;
}

/** The frame to draw at wall time ``now`` from the arrived frames (null before any arrive). */
export function frameAt(frames: ArrivedFrame[], now: number, speed: number): Frame | null {
  if (frames.length === 0) return null;
  const last = frames[frames.length - 1];
  const target = last.t - DELAY_S + Math.min(DELAY_S, ((now - last.arrived) / 1000) * speed);
  const same = frames.filter((f) => f.period === last.period);
  for (let i = same.length - 1; i > 0; i--) {
    if (same[i - 1].t <= target) return interpolate(same[i - 1], same[i], target);
  }
  return same[0];
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function drawLines(ctx: CanvasRenderingContext2D, s: number): void {
  ctx.strokeStyle = cssVar("--mm-pitch-line") || "rgba(255,255,255,.28)";
  ctx.lineWidth = Math.max(1, s * 0.12);
  const r = (x: number, y: number, w: number, h: number) => ctx.strokeRect(x * s, y * s, w * s, h * s);
  r(0, 0, LENGTH, WIDTH);
  ctx.beginPath();
  ctx.moveTo((LENGTH / 2) * s, 0);
  ctx.lineTo((LENGTH / 2) * s, WIDTH * s);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc((LENGTH / 2) * s, (WIDTH / 2) * s, 9.15 * s, 0, Math.PI * 2);
  ctx.stroke();
  r(0, (WIDTH - 40.3) / 2, 16.5, 40.3);
  r(LENGTH - 16.5, (WIDTH - 40.3) / 2, 16.5, 40.3);
  r(0, (WIDTH - 18.3) / 2, 5.5, 18.3);
  r(LENGTH - 5.5, (WIDTH - 18.3) / 2, 5.5, 18.3);
}

function draw(ctx: CanvasRenderingContext2D, f: Frame | null, colors: PitchColors, s: number): void {
  ctx.fillStyle = cssVar("--mm-pitch") || "#0f1f17";
  ctx.fillRect(0, 0, LENGTH * s, WIDTH * s);
  drawLines(ctx, s);
  if (!f) return;
  for (const p of f.players) {
    ctx.beginPath();
    ctx.arc(p.x * s, (WIDTH - p.y) * s, 1.05 * s, 0, Math.PI * 2);
    ctx.fillStyle = p.team_id === colors.homeId ? colors.home : colors.away;
    ctx.fill();
    ctx.lineWidth = Math.max(1.5, s * 0.25);
    ctx.strokeStyle = "#FFFFFF";
    ctx.stroke();
  }
  const [bx, by, bz] = f.ball;
  ctx.beginPath();
  ctx.arc(bx * s, (WIDTH - by) * s, (0.55 + Math.min(bz, 3) * 0.12) * s, 0, Math.PI * 2);
  ctx.fillStyle = "#FFFFFF";
  ctx.shadowColor = "rgba(0,0,0,.6)";
  ctx.shadowBlur = s * 0.6;
  ctx.fill();
  ctx.shadowBlur = 0;
}

export default function Pitch({ colors, label }: { colors: PitchColors; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    let raf = 0;
    const loop = () => {
      const ratio = window.devicePixelRatio || 1;
      const cssWidth = canvas.clientWidth || 700;
      const w = Math.round(cssWidth * ratio);
      if (canvas.width !== w) {
        canvas.width = w;
        canvas.height = Math.round((w * WIDTH) / LENGTH);
      }
      const { frames, speed, playing } = useStore.getState();
      draw(ctx, frameAt(frames, playing ? performance.now() : frames.at(-1)?.arrived ?? 0, speed), colors, w / LENGTH);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [colors]);

  return (
    <div dir="ltr" className="relative">
      <canvas ref={ref} role="img" aria-label={label} className="block aspect-[105/68] w-full" />
    </div>
  );
}
