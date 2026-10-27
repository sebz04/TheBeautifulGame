// The interface's words in five languages. Agent texts arrive already written in the
// fan's language; these are the labels, buttons, and messages around them.
import type { Lang } from "../api/types";
import { useStore } from "../state/store";
import ar from "./ar.json";
import en from "./en.json";
import es from "./es.json";
import fr from "./fr.json";
import pt from "./pt.json";

export type Key = keyof typeof en;
type Dict = Record<string, string>;

const DICTS: Record<Lang, Dict> = { en, es, pt, fr, ar };
export const LANG_NAMES: Record<Lang, string> = { en: "English", es: "Español", pt: "Português", fr: "Français", ar: "العربية" };

/** ``key`` in ``lang`` with ``{placeholders}`` filled; English if missing, the key if unknown. */
export function translate(lang: Lang, key: string, vars: Record<string, string | number> = {}): string {
  const text = DICTS[lang]?.[key] ?? (en as Dict)[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`));
}

/** Set the page's language and direction (Arabic reads right to left). */
export function setLang(lang: Lang): void {
  document.documentElement.setAttribute("lang", lang);
  document.documentElement.setAttribute("dir", lang === "ar" ? "rtl" : "ltr");
}

/** The translate function for the fan's chosen language. */
export function useT(): (key: Key, vars?: Record<string, string | number>) => string {
  const lang = useStore((s) => s.prefs.lang);
  return (key, vars) => translate(lang, key, vars);
}
