// Both teams' numbers side by side at the replay's time.
import { api } from "../api/client";
import type { Period } from "../api/types";
import { useAsync } from "../lib/useAsync";
import { LoadError, Loading } from "./Status";

const TEAM_NAMES: Record<string, (v: number) => string> = {
  goals: (v) => String(v), xg: (v) => v.toFixed(2), possession: (v) => `${Math.round(v * 100)}%`,
  territory: (v) => `${Math.round(v * 100)}%`, shots: (v) => String(v), shots_on_target: (v) => String(v),
  passes: (v) => String(v), pass_completion: (v) => `${Math.round(v * 100)}%`, ppda: (v) => v.toFixed(1),
  field_tilt_10min: (v) => `${Math.round(v * 100)}%`, corners: (v) => String(v), fouls: (v) => String(v),
  yellow: (v) => String(v), red: (v) => String(v),
}; // prettier-ignore

const LABELS: Record<string, string> = {
  goals: "Goals", xg: "Expected goals", possession: "Possession", territory: "Territory", shots: "Shots",
  shots_on_target: "On target", passes: "Passes", pass_completion: "Pass completion", ppda: "Passes per defensive action",
  field_tilt_10min: "Final-third share, last 10 min", corners: "Corners", fouls: "Fouls", yellow: "Yellow cards", red: "Red cards",
}; // prettier-ignore

export interface TeamTabProps {
  matchId: string;
  home: { club_id: string; name: string };
  away: { club_id: string; name: string };
  period: Period;
  t: number;
}

export default function TeamTab({ matchId, home, away, period, t }: TeamTabProps) {
  const at = Math.floor(t / 30) * 30;
  const state = useAsync(
    () => Promise.all([home, away].map((c) => api.stats(matchId, { scope: "team", scope_id: c.club_id, period, t: at }))),
    [matchId, home.club_id, away.club_id, period, at],
  );
  if (state.status === "loading") return <Loading what="the team stats" />;
  if (state.status === "error") return <LoadError what="the team stats" retry={state.retry} />;
  const [h, a] = state.data.map((s) => s.metrics);
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="text-muted">
          <th className="py-2 text-left font-medium">{home.name}</th>
          <th className="py-2 font-medium" />
          <th className="py-2 text-right font-medium">{away.name}</th>
        </tr>
      </thead>
      <tbody>
        {Object.keys(LABELS).map((k) => (
          <tr key={k} className="border-t border-[color:var(--mm-rule)]">
            <td className="py-2 text-left font-display text-xl font-extrabold tabular-nums">{h[k] == null ? "–" : TEAM_NAMES[k](h[k]!)}</td>
            <td className="py-2 text-center text-muted">{LABELS[k]}</td>
            <td className="py-2 text-right font-display text-xl font-extrabold tabular-nums">{a[k] == null ? "–" : TEAM_NAMES[k](a[k]!)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
