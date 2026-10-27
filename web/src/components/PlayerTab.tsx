// A player's match so far against what their season says to expect by now.
import { useState } from "react";

import { api } from "../api/client";
import type { Period } from "../api/types";
import { useAsync } from "../lib/useAsync";
import { LoadError, Loading } from "./Status";

export const STAT_NAMES: Record<string, string> = {
  passes: "Passes", completed: "Completed passes", forward_passes: "Forward passes", progressive_passes: "Progressive passes",
  shots: "Shots", shots_on_target: "Shots on target", goals: "Goals", assists: "Assists", tackles: "Tackles",
  interceptions: "Interceptions", dribbles: "Dribbles", touches_box: "Touches in the box", sprints: "Sprints",
  key_passes: "Key passes", xg: "Expected goals", distance_km: "Distance (km)", top_speed_kmh: "Top speed (km/h)",
}; // prettier-ignore

const show = (v: number | null | undefined) => (v == null ? "–" : Number.isInteger(v) ? String(v) : v.toFixed(1));

export interface PlayerTabProps {
  matchId: string;
  players: { player_id: string; name: string }[];
  playerId: string;
  period: Period;
  t: number;
}

export default function PlayerTab({ matchId, players, playerId, period, t }: PlayerTabProps) {
  const [chosen, setChosen] = useState(playerId);
  const at = Math.floor(t / 30) * 30; // refresh every 30 s of match time
  const state = useAsync(() => api.stats(matchId, { scope: "player", scope_id: chosen, period, t: at }), [matchId, chosen, period, at]);
  return (
    <div className="p-1">
      <label className="mb-3 flex items-center gap-2 text-sm text-muted">
        Player
        <select value={chosen} onChange={(e) => setChosen(e.target.value)} className="border border-[color:var(--mm-rule)] bg-surface px-2 py-1.5 text-text">
          {players.map((p) => (
            <option key={p.player_id} value={p.player_id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      {state.status === "loading" && <Loading what="the player's stats" />}
      {state.status === "error" && <LoadError what="the player's stats" retry={state.retry} />}
      {state.status === "ready" && (
        <>
          {!state.data.baseline && <p className="text-sm text-muted">No season data for this player yet, so there's no expectation to compare with.</p>}
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left text-muted">
                <th className="py-2 font-medium">Stat</th>
                <th className="py-2 text-right font-medium">This match</th>
                {state.data.baseline && <th className="py-2 text-right font-medium">Season says by now</th>}
              </tr>
            </thead>
            <tbody>
              {Object.entries(state.data.metrics)
                .filter(([k]) => k in STAT_NAMES)
                .map(([k, v]) => (
                  <tr key={k} className="border-t border-[color:var(--mm-rule)]">
                    <td className="py-2">{STAT_NAMES[k]}</td>
                    <td className="py-2 text-right font-display text-xl font-extrabold tabular-nums">{show(v)}</td>
                    {state.data.baseline && <td className="py-2 text-right tabular-nums text-muted">{show(state.data.baseline[k])}</td>}
                  </tr>
                ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
