import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { MatchDetail, PitchControl } from "../api/types";
import MomentumChart from "../components/MomentumChart";
import Overlays from "../components/Overlays";
import Pitch from "../components/Pitch";
import PlaybackBar from "../components/PlaybackBar";
import RealismPanel from "../components/RealismPanel";
import StatsStrip from "../components/StatsStrip";
import { LoadError, Loading } from "../components/Status";
import Timeline from "../components/Timeline";
import { useAsync } from "../lib/useAsync";
import { minuteLabel } from "../live/minute";
import { scoreAt } from "../live/score";
import { useStore } from "../state/store";

const HALF_S = 45 * 60;
const HEAT_EVERY_MS = 1000;

/** The pitch-control heatmap for the replay's time while ``on`` (at most once a second). */
function useHeat(matchId: string, on: boolean): PitchControl | null {
  const [heat, setHeat] = useState<PitchControl | null>(null);
  useEffect(() => {
    if (!on) {
      setHeat(null);
      return;
    }
    let live = true;
    const load = () => {
      const { period, t } = useStore.getState();
      api.pitchControl(matchId, period, Math.floor(t * 10) / 10).then((h) => live && setHeat(h), () => undefined);
    };
    load();
    const timer = setInterval(() => useStore.getState().playing && load(), HEAT_EVERY_MS);
    const unsub = useStore.subscribe((s, prev) => !s.playing && (s.t !== prev.t || s.period !== prev.period) && load());
    return () => {
      live = false;
      clearInterval(timer);
      unsub();
    };
  }, [matchId, on]);
  return heat;
}

function Monogram({ club, solid }: { club: MatchDetail["home"]; solid?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className="grid h-11 w-11 place-items-center border-2 font-display text-xl font-black"
      style={solid ? { background: club.primary_color, borderColor: club.primary_color, color: "#fff" } : {}}
    >
      {club.short}
    </span>
  );
}

/** Layout B: score bar, switches, pitch (left) and pundit (right), then stats and the match flow.
 * The panels are filled in by later tasks (pitch 23.2, overlays and charts 23.3, insights 23.4,
 * switches 23.5). */
export default function Match() {
  const { id = "" } = useParams();
  const state = useAsync(() => api.match(id), [id]);
  const timeline = useAsync(() => api.timeline(id), [id]);
  const [about, setAbout] = useState(false);
  const [showHeat, setShowHeat] = useState(false);
  const heat = useHeat(id, showHeat);
  const live = useStore();
  const openMatch = useStore((x) => x.openMatch);
  useEffect(() => openMatch(id), [id, openMatch]);
  const colors = useMemo(
    () =>
      state.status === "ready"
        ? { home: state.data.home.primary_color, away: state.data.away.primary_color, homeId: state.data.home.club_id }
        : { home: "#888", away: "#444", homeId: "" },
    [state],
  );

  if (state.status === "loading") return <main className="px-7"><Loading what="the match" /></main>;
  if (state.status === "error") return <main className="px-7 py-8"><LoadError what="the match" retry={state.retry} /></main>;
  const m = state.data;
  const firstHalfS = HALF_S + m.added_time_s[0];
  const minute = minuteLabel(live.period, live.t, m.added_time_s);
  const moments = timeline.status === "ready" ? timeline.data.moments : [];
  const score = scoreAt(moments, live.period, live.t, m.home.club_id);
  const totalS = firstHalfS + HALF_S + m.added_time_s[1];
  const names = Object.fromEntries([...m.home_squad, ...m.away_squad].map((p) => [p.player_id, p.name]));
  const latest = live.frames.at(-1);
  const positions = Object.fromEntries((latest?.players ?? []).map((p) => [p.player_id, { x: p.x, y: p.y }]));
  const teamColors = { "--mm-home": m.home.primary_color, "--mm-away": m.away.primary_color } as React.CSSProperties;

  return (
    <main className="mx-auto max-w-[1280px] px-4 pb-10 pt-5 md:px-7" style={teamColors}>
      <header aria-label="Score" className="grid grid-cols-[1fr_auto_1fr] items-center gap-6">
        <div className="flex items-center gap-3.5 font-bold">
          <Monogram club={m.home} />
          <span className="hidden sm:inline">{m.home.name}</span>
        </div>
        <div className="flex items-baseline gap-4 font-display text-6xl font-black leading-none tabular-nums md:text-7xl">
          <span>{score.home}</span>
          <span className="bg-accent px-2.5 py-1.5 text-2xl font-extrabold text-on-accent">{minute}</span>
          <span>{score.away}</span>
        </div>
        <div className="flex items-center justify-end gap-3.5 font-bold">
          <span className="hidden sm:inline">{m.away.name}</span>
          <Monogram club={m.away} solid />
        </div>
      </header>

      <div className="my-4 flex flex-wrap items-center gap-3 text-sm">
        <Link to="/matches" className="text-text-on-bg">All matches</Link>
        <button type="button" onClick={() => setAbout(true)} className="border-0 bg-transparent p-0 text-sm text-text-on-bg underline">
          About this match
        </button>
      </div>

      {about && (
        <RealismPanel
          realism={m.realism}
          clubs={{ [m.home.club_id]: m.home.name, [m.away.club_id]: m.away.name }}
          onClose={() => setAbout(false)}
        />
      )}

      <div className="grid items-start gap-5 md:grid-cols-[7fr_5fr]">
        <section aria-label="Match" className="bg-surface p-3.5 text-text">
          <Pitch colors={colors} label={`Live pitch at ${minute}`} heat={heat}>
            <Overlays cues={live.cues} period={live.period} t={live.t} names={names} positions={positions} />
          </Pitch>
          <PlaybackBar
            playing={live.playing}
            speed={live.speed}
            period={live.period}
            t={live.t}
            firstHalfS={firstHalfS}
            secondHalfS={HALF_S + m.added_time_s[1]}
            onToggle={() => (live.playing ? live.pause() : live.play())}
            onSpeed={live.setSpeed}
            onSeek={live.seek}
          />
          <label className="mt-3 flex items-center gap-2 text-sm text-muted">
            <input type="checkbox" checked={showHeat} onChange={(e) => setShowHeat(e.target.checked)} className="h-4 w-4 accent-[color:var(--mm-accent)]" />
            Show which team controls each area of the pitch
          </label>
          {live.connection === "reconnecting" && <p role="status" className="mt-2 text-sm text-warn">Reconnecting to the match…</p>}
        </section>
        <aside aria-label="Your pundit" className="order-first bg-surface p-6 text-text md:order-none" data-slot="pundit" />
      </div>

      <div className="mt-5">
        <StatsStrip matchId={id} homeId={m.home.club_id} awayId={m.away.club_id} period={live.period} t={live.t} />
      </div>
      <section aria-label="How the match has swung" className="mt-0.5 bg-surface px-4 pb-4 pt-3 text-text">
        <Timeline moments={moments} firstHalfS={firstHalfS} totalS={totalS} period={live.period} t={live.t} addedS={m.added_time_s} onSeek={live.seek} />
        {timeline.status === "ready" && (
          <MomentumChart points={timeline.data.momentum} firstHalfS={firstHalfS} totalS={totalS} period={live.period} t={live.t} homeName={m.home.name} awayName={m.away.name} />
        )}
      </section>
    </main>
  );
}
