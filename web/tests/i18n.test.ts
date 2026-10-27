import { describe, expect, it } from "vitest";

import ar from "../src/i18n/ar.json";
import en from "../src/i18n/en.json";
import es from "../src/i18n/es.json";
import fr from "../src/i18n/fr.json";
import pt from "../src/i18n/pt.json";
import { setLang, translate } from "../src/i18n/i18n";

const PLACEHOLDER = /\{(\w+)\}/g;

describe("i18n", () => {
  for (const [lang, dict] of Object.entries({ es, pt, fr, ar })) {
    it(`${lang} has exactly the English keys, with the same placeholders`, () => {
      expect(Object.keys(dict).sort()).toEqual(Object.keys(en).sort());
      for (const [key, text] of Object.entries(en)) {
        const want = [...text.matchAll(PLACEHOLDER)].map((m) => m[1]).sort();
        const got = [...(dict as Record<string, string>)[key].matchAll(PLACEHOLDER)].map((m) => m[1]).sort();
        expect(got, `${lang}.${key}`).toEqual(want);
      }
    });
  }

  it("fills placeholders and falls back to English", () => {
    expect(translate("es", "loading", { what: "x" })).toMatch(/x/);
    expect(translate("en", "missing.key.for.test")).toBe("missing.key.for.test");
  });

  it("sets lang and dir on <html>", () => {
    setLang("ar");
    expect(document.documentElement).toHaveAttribute("lang", "ar");
    expect(document.documentElement).toHaveAttribute("dir", "rtl");
    setLang("fr");
    expect(document.documentElement).toHaveAttribute("dir", "ltr");
  });
});
