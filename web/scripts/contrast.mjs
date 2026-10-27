// Checks the text/background pairs a mockup declares (<script id="contrast-pairs">)
// against its :root CSS variables. Usage: node scripts/contrast.mjs mockups/*.html
import { readFileSync } from "node:fs";

const lum = (hex) => {
  const n = parseInt(hex.replace("#", ""), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
};
const ratio = (a, b) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

let failed = 0;
for (const file of process.argv.slice(2)) {
  const html = readFileSync(file, "utf8");
  const root = html.match(/:root\s*{([^}]*)}/)[1];
  const vars = Object.fromEntries([...root.matchAll(/(--[\w-]+):\s*(#[0-9A-Fa-f]{6})/g)].map((m) => [m[1], m[2]]));
  const pairs = JSON.parse(html.match(/id="contrast-pairs">([\s\S]*?)<\/script>/)[1]);
  console.log(file);
  for (const [fg, bg, min] of pairs) {
    const r = ratio(vars[fg], vars[bg]);
    const ok = r >= min;
    failed += ok ? 0 : 1;
    console.log(`  ${ok ? "pass" : "FAIL"}  ${fg} ${vars[fg]} on ${bg} ${vars[bg]}: ${r.toFixed(2)} (min ${min})`);
  }
}
process.exit(failed ? 1 : 0);
