// What the match page and the Best Plays tab share: the match, its timeline, the fan's
// voice (from the switches), their insights in that voice, and the club color takeover.
import { useEffect, useMemo } from "react";

import { api } from "../api/client";
import type { InsightRow, MatchDetail, Timeline } from "../api/types";
import { NEUTRAL_THEME, applyTheme, clubTheme } from "../design/theme";
import { personaFor, themeClubFor, type MatchSides, type Voice } from "../persona";
import { useStore } from "../state/store";
import { useAsync, type AsyncState } from "./useAsync";

export interface FanMatch {
  match: AsyncState<MatchDetail>;
  timeline: AsyncState<Timeline>;
  rows: AsyncState<InsightRow[]>;
  /** The voice for the insights, or null while the fan still has to pick a side. */
  voice: Voice | null;
  needsSide: boolean;
  themeClub: string | null;
}

export function useFanMatch(id: string): FanMatch {
  const prefs = useStore((s) => s.prefs);
  const openMatch = useStore((s) => s.openMatch);
  useEffect(() => openMatch(id), [id, openMatch]);

  const match = useAsync(() => api.match(id), [id]);
  const timeline = useAsync(() => api.timeline(id), [id]);
  const sides: MatchSides | null = useMemo(
    () =>
      match.status === "ready"
        ? { match_id: id, home: match.data.home, away: match.data.away,
            players: [...match.data.home_squad, ...match.data.away_squad].map((p) => p.player_id) } // prettier-ignore
        : null,
    [match, id],
  );
  const picked = sides ? personaFor(prefs, sides) : null;
  const voice: Voice | null = picked && !("needsSide" in picked) ? picked : null;
  const voiceKey = voice ? `${voice.persona}:${voice.club_id ?? ""}:${voice.player_id ?? ""}` : "";
  const rows = useAsync(
    () => (voice ? api.insights(id, { ...voice, lang: prefs.lang }) : new Promise<never>(() => undefined)),
    [id, prefs.lang, voiceKey],
  );
  const themeClub = sides ? themeClubFor(prefs, sides) : null;

  useEffect(() => {
    const club = match.status === "ready" ? [match.data.home, match.data.away].find((c) => c.club_id === themeClub) : undefined;
    applyTheme(club ? clubTheme(club, "dark") : NEUTRAL_THEME);
  }, [match, themeClub]);

  return { match, timeline, rows, voice, needsSide: Boolean(picked && "needsSide" in picked), themeClub };
}
