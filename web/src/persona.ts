// The fan's switches (Team ⇄ Player, Fan ⇄ Scout) mapped onto the agents' four voices
// (docs/design.md): Team + Fan → club_fan (or pick a side; casual without a club),
// Team + Scout → analyst, Player → player_focus while that player is in the match.
import type { Persona } from "./api/types";
import type { Prefs } from "./state/prefs";

export interface MatchSides {
  match_id: string;
  home: { club_id: string };
  away: { club_id: string };
  players: string[];
}

export type Voice = { persona: Persona; club_id?: string; player_id?: string };

/** The club whose colors take over this match: the favorite if playing, else the side
 * picked for it, else null (the neutral theme). */
export function themeClubFor(prefs: Prefs, match: MatchSides): string | null {
  const clubs = [match.home.club_id, match.away.club_id];
  if (prefs.favorite_club_id && clubs.includes(prefs.favorite_club_id)) return prefs.favorite_club_id;
  const side = prefs.sides[match.match_id];
  return side && clubs.includes(side) ? side : null;
}

export function personaFor(prefs: Prefs, match: MatchSides): Voice | { needsSide: true } {
  if (prefs.focus === "player" && prefs.favorite_player_id && match.players.includes(prefs.favorite_player_id)) {
    return { persona: "player_focus", player_id: prefs.favorite_player_id };
  }
  if (prefs.mode === "scout") return { persona: "analyst" };
  if (!prefs.favorite_club_id) return { persona: "casual" };
  const club = themeClubFor(prefs, match);
  return club ? { persona: "club_fan", club_id: club } : { needsSide: true };
}
