import { useEffect } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { MatchRow } from "../api/types";
import { LoadError, Loading } from "../components/Status";
import { NEUTRAL_THEME, applyTheme, clubTheme } from "../design/theme";
import { useT } from "../i18n/i18n";
import { useAsync } from "../lib/useAsync";
import { useStore } from "../state/store";

/** The fan's club's matches first, then the rest in their original order. */
export function orderForFan(rows: MatchRow[], clubId: string | null): MatchRow[] {
  const mine = (r: MatchRow) => clubId !== null && (r.home.club_id === clubId || r.away.club_id === clubId);
  return [...rows.filter(mine), ...rows.filter((r) => !mine(r))];
}

function Monogram({ club }: { club: MatchRow["home"] }) {
  return (
    <span
      aria-hidden="true"
      className="grid h-11 w-11 shrink-0 place-items-center font-display text-lg font-black"
      style={{ background: club.primary_color, color: "#fff", outline: "2px solid rgba(255,255,255,.6)" }}
    >
      {club.short}
    </span>
  );
}

export default function MatchPicker() {
  const t = useT();
  const clubId = useStore((s) => s.prefs.favorite_club_id);
  const state = useAsync(() => api.matches(), []);
  useEffect(() => {
    const rows = state.status === "ready" ? state.data : [];
    const club = rows.flatMap((r) => [r.home, r.away]).find((c) => c.club_id === clubId);
    applyTheme(club ? clubTheme(club, "dark") : NEUTRAL_THEME);
  }, [state, clubId]);

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 md:px-7">
      <h1 className="m-0 mb-6 font-display text-5xl font-black leading-none">{t("picker.title")}</h1>
      <p className="-mt-3 mb-6 text-sm">
        <Link to="/welcome" className="text-text-on-bg">{t("welcome.change")}</Link>
      </p>
      {state.status === "loading" && <Loading what="what.matches" />}
      {state.status === "error" && <LoadError what="what.matches" retry={state.retry} />}
      {state.status === "ready" && (
        <ul className="m-0 grid list-none gap-0.5 p-0">
          {orderForFan(state.data, clubId).map((m) => {
            const yours = clubId !== null && (m.home.club_id === clubId || m.away.club_id === clubId);
            return (
              <li key={m.match_id}>
                <Link
                  to={`/match/${m.match_id}`}
                  className="flex items-center gap-4 bg-surface p-4 text-text no-underline hover:bg-black"
                >
                  <Monogram club={m.home} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-base font-bold">{m.title}</span>
                    {yours && <span className="text-sm text-muted">{t("picker.yours")}</span>}
                  </span>
                  <span className="font-display text-4xl font-black tabular-nums">
                    {m.score.home}–{m.score.away}
                  </span>
                  <Monogram club={m.away} />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
