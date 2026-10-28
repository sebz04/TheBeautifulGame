// First visit: what MatchMind is, then the fan sets it up (club, player, language, how they
// watch). The page speaks the language being chosen and recolors to the club being chosen.
import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { Lang } from "../api/types";
import { LoadError, Loading } from "../components/Status";
import { NEUTRAL_THEME, applyTheme, clubTheme, textOn } from "../design/theme";
import { LANG_NAMES, setLang, translate } from "../i18n/i18n";
import { useAsync } from "../lib/useAsync";
import { hasSavedPrefs, type Mode, type Prefs } from "../state/prefs";
import { useStore } from "../state/store";

export default function Welcome({ forceSetup = false }: { forceSetup?: boolean }) {
  const prefs = useStore((s) => s.prefs);
  const setPrefs = useStore((s) => s.setPrefs);
  const navigate = useNavigate();
  const [draft, setDraft] = useState<Prefs>({ ...prefs, sides: { ...prefs.sides } });
  const league = useAsync(() => api.league(), []);
  const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate(draft.lang, key, vars);
  const club = league.status === "ready" ? league.data.clubs.find((c) => c.club_id === draft.favorite_club_id) : undefined;

  useEffect(() => setLang(draft.lang), [draft.lang]);
  useEffect(() => applyTheme(club ? clubTheme(club, "dark") : NEUTRAL_THEME), [club]);

  if (!forceSetup && hasSavedPrefs()) return <Navigate to="/matches" replace />;

  const pick = (patch: Partial<Prefs>) => setDraft((d) => ({ ...d, ...patch }));
  // With a club picked, go straight to its first showcase match (the list when it has none,
  // or when the list can't be read); "All matches" is one click away in the match header.
  const start = async () => {
    setPrefs(draft);
    const clubId = draft.favorite_club_id;
    const rows = clubId ? await api.matches().catch(() => []) : [];
    const first = rows.find((r) => r.home.club_id === clubId || r.away.club_id === clubId);
    navigate(first ? `/match/${first.match_id}` : "/matches");
  };

  return (
    <main className="mx-auto max-w-5xl px-4 pb-12 pt-10 md:px-7">
      <h1 className="m-0 font-display text-6xl font-black leading-[0.92] md:text-8xl">{t("welcome.title")}</h1>
      <p className="mb-10 mt-4 max-w-[52ch] text-lg">{t("welcome.intro")}</p>

      {league.status === "loading" && <Loading what="what.league" />}
      {league.status === "error" && <LoadError what="what.league" retry={league.retry} />}
      {league.status === "ready" && (
        <div className="grid gap-8 bg-surface p-6 text-text md:p-8">
          <section>
            <h2 id="club-label" className="m-0 mb-3 text-sm font-bold text-muted">
              {t("welcome.club")}
            </h2>
            <div role="group" aria-labelledby="club-label" className="grid grid-cols-2 gap-1.5 sm:grid-cols-4 lg:grid-cols-5">
              {league.data.clubs.map((c) => {
                const chosen = draft.favorite_club_id === c.club_id;
                return (
                  <button
                    key={c.club_id}
                    type="button"
                    aria-pressed={chosen}
                    onClick={() => pick({ favorite_club_id: chosen ? null : c.club_id, favorite_player_id: null })}
                    className={`flex min-h-20 flex-col justify-end border-0 p-3 text-start ${chosen ? "outline outline-[3px] outline-offset-2 outline-[color:var(--mm-text)]" : ""}`}
                    style={{ background: c.primary_color, color: textOn(c.primary_color) }}
                  >
                    <span aria-hidden="true" className="font-display text-2xl font-black leading-none">
                      {c.short}
                    </span>
                    <span className="text-sm font-bold">{c.name}</span>
                  </button>
                );
              })}
            </div>
          </section>

          <div className="grid gap-6 sm:grid-cols-2">
            <label className="grid gap-2 text-sm font-bold text-muted">
              {t("welcome.player")}
              <select
                value={draft.favorite_player_id ?? ""}
                onChange={(e) => pick({ favorite_player_id: e.target.value || null })}
                disabled={!draft.favorite_club_id}
                className="border border-[color:var(--mm-rule)] bg-surface px-3 py-2.5 text-base font-normal text-text disabled:opacity-50"
              >
                <option value="">{t("welcome.noPlayer")}</option>
                {league.data.players
                  .filter((p) => p.club_id === draft.favorite_club_id)
                  .map((p) => (
                    <option key={p.player_id} value={p.player_id}>
                      {p.name}
                    </option>
                  ))}
              </select>
            </label>
            <label className="grid gap-2 text-sm font-bold text-muted">
              {t("welcome.language")}
              <select
                value={draft.lang}
                onChange={(e) => pick({ lang: e.target.value as Lang })}
                className="border border-[color:var(--mm-rule)] bg-surface px-3 py-2.5 text-base font-normal text-text"
              >
                {(Object.keys(LANG_NAMES) as Lang[]).map((l) => (
                  <option key={l} value={l} lang={l}>
                    {LANG_NAMES[l]}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <fieldset className="m-0 border-0 p-0">
            <legend className="mb-3 p-0 text-sm font-bold text-muted">{t("welcome.how")}</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {(["fan", "scout"] as Mode[]).map((mode) => (
                <label
                  key={mode}
                  className={`flex cursor-pointer gap-3 border-2 p-4 ${draft.mode === mode ? "border-accent" : "border-[color:var(--mm-rule)]"}`}
                >
                  <input type="radio" name="mode" value={mode} checked={draft.mode === mode} onChange={() => pick({ mode })} className="mt-1 h-4 w-4 accent-[color:var(--mm-accent)]" />
                  <span>
                    <span className="block font-display text-2xl font-extrabold">{t(mode === "fan" ? "bar.fan" : "bar.scout")}</span>
                    <span className="text-sm text-muted">{t(mode === "fan" ? "welcome.fanHint" : "welcome.scoutHint")}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <div>
            <button type="button" onClick={start} className="border-0 bg-accent px-6 py-3.5 text-lg font-bold text-on-accent">
              {t("welcome.start")}
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
