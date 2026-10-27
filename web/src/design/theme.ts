/**
 * The club takeover: a club's two colors become the page's CSS variables, adjusted so
 * every text and background pair meets WCAG AA (4.5:1).
 *
 * The primary stays exactly the club's color as the page field (`--mm-bg`); text on it is
 * near-black or white, whichever reads better. The secondary is the accent, nudged in
 * lightness until its own text passes. Cards are a fixed dark or light surface.
 */

export type ThemeVars = Record<string, string>;
export type Surface = "dark" | "light";

const AA = 4.5;
const INK = "#0E0E12"; // near-black text
const PAPER = "#FFFFFF";
const SURFACES: Record<Surface, { surface: string; text: string; muted: string }> = {
  dark: { surface: "#121216", text: "#F4F4F6", muted: "#A9A9B6" },
  light: { surface: "#FFFFFF", text: "#16161C", muted: "#5C5C6B" },
};
const GOOD = { dark: "#4ADE80", light: "#15803D" };
const WARN = { dark: "#FBBF24", light: "#B45309" };

type Rgb = [number, number, number];

function hexToRgb(hex: string): Rgb {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? [...h].map((c) => c + c).join("") : h;
  const n = parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex([r, g, b]: Rgb): string {
  return "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("").toUpperCase();
}

function luminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** The WCAG contrast ratio of two colors (1 to 21), in either order. */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Near-black or white, whichever has the higher contrast on `bg`. */
function textOn(bg: string): string {
  return contrast(INK, bg) >= contrast(PAPER, bg) ? INK : PAPER;
}

function toHsl([r, g, b]: Rgb): [number, number, number] {
  const [rr, gg, bb] = [r / 255, g / 255, b / 255];
  const max = Math.max(rr, gg, bb);
  const min = Math.min(rr, gg, bb);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h =
    max === rr ? (gg - bb) / d + (gg < bb ? 6 : 0) : max === gg ? (bb - rr) / d + 2 : (rr - gg) / d + 4;
  return [h / 6, s, l];
}

function fromHsl([h, s, l]: [number, number, number]): Rgb {
  if (s === 0) return [l * 255, l * 255, l * 255];
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const hue = (t: number): number => {
    const tt = t < 0 ? t + 1 : t > 1 ? t - 1 : t;
    if (tt < 1 / 6) return p + (q - p) * 6 * tt;
    if (tt < 1 / 2) return q;
    if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6;
    return p;
  };
  return [hue(h + 1 / 3) * 255, hue(h) * 255, hue(h - 1 / 3) * 255];
}

/** `color` moved in lightness, in small steps, until its best text color passes AA. */
function readableAccent(color: string): string {
  let [h, s, l] = toHsl(hexToRgb(color));
  const darken = textOn(color) === PAPER; // move away from the text color
  for (let i = 0; i < 40 && contrast(textOn(color), color) < AA; i++) {
    l = Math.min(1, Math.max(0, l + (darken ? -0.02 : 0.02)));
    color = rgbToHex(fromHsl([h, s, l]));
  }
  return color;
}

function build(field: string, accentBase: string, surface: Surface): ThemeVars {
  const s = SURFACES[surface];
  const accent = readableAccent(accentBase);
  return {
    "--mm-bg": field,
    "--mm-text-on-bg": textOn(field),
    "--mm-surface": s.surface,
    "--mm-text": s.text,
    "--mm-muted": s.muted,
    "--mm-accent": accent,
    "--mm-on-accent": textOn(accent),
    "--mm-good": GOOD[surface],
    "--mm-warn": WARN[surface],
  };
}

/** The page's variables for a club; ``surface`` is the card color of the chosen direction. */
export function clubTheme(
  club: { primary_color: string; secondary_color: string },
  surface: Surface = "dark",
): ThemeVars {
  const primary = club.primary_color.toUpperCase();
  let secondary = club.secondary_color.toUpperCase();
  if (contrast(primary, secondary) < 1.5) secondary = textOn(primary); // too close to tell apart
  return build(primary, secondary, surface);
}

/** Before a club is chosen: a graphite field with a bright, club-free accent. */
export const NEUTRAL_THEME: ThemeVars = build("#1C1C22", "#E8E8EE", "dark");

/** Set the variables on the page (the club takeover). */
export function applyTheme(vars: ThemeVars, root: HTMLElement = document.documentElement): void {
  for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value);
}
