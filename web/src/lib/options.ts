// How a decision option reads to a fan: "Through ball to Jhojan Monero", "54% to work",
// "+0.11 danger" (xT added) or "no added danger".
import type { Option } from "../api/types";
import type { Key } from "../i18n/i18n";

export type T = (key: Key, vars?: Record<string, string | number>) => string;

export function optionWhat(o: Option, names: Record<string, string>, t: T): string {
  const kind = t(`opt.${o.kind}` as Key);
  return o.target_player_id ? t("opt.to", { kind, player: names[o.target_player_id] ?? t("opt.teammate") }) : kind;
}

export function dangerText(o: Option, t: T): string {
  return Math.abs(o.xt_gain) < 0.005 ? t("opt.noDanger") : t("opt.danger", { value: `${o.xt_gain > 0 ? "+" : ""}${o.xt_gain.toFixed(2)}` });
}

export function optionLine(o: Option, names: Record<string, string>, t: T): string {
  return t("opt.line", { what: optionWhat(o, names, t), chance: Math.round(o.pc_prob * 100), danger: dangerText(o, t) });
}
