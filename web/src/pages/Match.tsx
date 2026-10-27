import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { InsightRow, MatchDetail, PitchControl } from "../api/types";
import AskWhyPanel from "../components/AskWhyPanel";
import InsightPanel from "../components/InsightPanel";
import MomentumChart from "../components/MomentumChart";
import Overlays from "../components/Overlays";
import Pitch from "../components/Pitch";
import PlaybackBar from "../components/PlaybackBar";
import PersonaBar from "../components/PersonaBar";
import PlayerTab from "../components/PlayerTab";
import RealismPanel from "../components/RealismPanel";
import RecapPanel from "../components/RecapPanel";
import SidePicker from "../components/SidePicker";
import StatsStrip from "../components/StatsStrip";
import { LoadError, Loading } from "../components/Status";
import TeamTab from "../components/TeamTab";
import Timeline from "../components/Timeline";
import { useT } from "../i18n/i18n";
import { useAsync } from "../lib/useAsync";
import { useFanMatch } from "../lib/useFanMatch";
import { minuteLabel } from "../live/minute";
import { scoreAt } from "../live/score";
import { useStore } from "../state/store";

const HALF_S = 45 * 60;
const TABS = ["game", "team", "player"] as const;
type Tab = (typeof TABS)[number];
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
  const fan = useFanMatch(id);
  const state = fan.match;
  const timeline = fan.timeline;
  const rows = fan.rows;
  const ready = fan.voice;
  const themeClub = fan.themeClub;
  const navigate = useNavigate();
  const [about, setAbout] = useState(false);
  const [showHeat, setShowHeat] = useState(false);
  const [tab, setTab] = useState<Tab>("game");
  const [asking, setAsking] = useState<InsightRow | null>(null);
  const t = useT();
  const prefs = useStore((s) => s.prefs);
  const setPrefs = useStore((s) => s.setPrefs);
  const lang = prefs.lang;
  const league = useAsync(() => api.league(), []);
  const heat = useHeat(id, showHeat);
  const live = useStore();
  const colors = useMemo(
    () =>
      state.status === "ready"
        ? { home: state.data.home.primary_color, away: state.data.away.primary_color, homeId: state.data.home.club_id }
        : { home: "#888", away: "#444", homeId: "" },
    [state],
  );

  if (state.status === "loading") return <main className="px-7"><Loading what="what.match" /></main>;
  if (state.status === "error") return <main className="px-7 py-8"><LoadError what="what.match" retry={state.retry} /></main>;
  const m = state.data;
  const firstHalfS = HALF_S + m.added_time_s[0];
  const minute = minuteLabel(live.period, live.t, m.added_time_s);
  const moments = timeline.status === "ready" ? timeline.data.moments : [];
  const score = scoreAt(moments, live.period, live.t, m.home.club_id);
  const totalS = firstHalfS + HALF_S + m.added_time_s[1];
  const names = Object.fromEntries([...m.home_squad, ...m.away_squad].map((p) => [p.player_id, p.name]));
  const latest = live.frames.at(-1);
  const positions = Object.fromEntries((latest?.players ?? []).map((p) => [p.player_id, { x: p.x, y: p.y }]));
  const momentById = Object.fromEntries(moments.map((x) => [x.moment_id, x]));
  const squad = [...m.home_squad, ...m.away_squad].map((p) => ({ player_id: p.player_id, name: p.name }));
  const leagueNames = league.status === "ready" ? Object.fromEntries([...league.data.clubs.map((c) => [c.club_id, c.name]), ...league.data.players.map((p) => [p.player_id, p.name])]) : {};
  const clubName = themeClub ? (themeClub === m.home.club_id ? m.home.name : m.away.name) : prefs.favorite_club_id ? (leagueNames[prefs.favorite_club_id] ?? null) : null;
  const playerName = prefs.favorite_player_id ? (names[prefs.favorite_player_id] ?? leagueNames[prefs.favorite_player_id] ?? null) : null;
  const teamColors = { "--mm-home": m.home.primary_color, "--mm-away": m.away.primary_color } as React.CSSProperties;

  return (
    <main className="mx-auto max-w-[1280px] px-4 pb-10 pt-5 md:px-7" style={teamColors}>
      {fan.needsSide && (
        <SidePicker home={m.home} away={m.away} onPick={(club) => setPrefs({ sides: { ...prefs.sides, [id]: club } })} />
      )}
      <header aria-label={t("match.score")} className="grid grid-cols-[1fr_auto_1fr] items-center gap-6">
        <div className="flex items-center gap-3.5 font-bold">
          <Monogram club={m.home} />
          <span className="hidden sm:inline">{m.home.name}</span>
        </div>
        <div className="flex items-baseline gap-4 font-display text-6xl font-black leading-none tabular-nums md:text-7xl">
          <span>{score.home}</span>
          <span dir="ltr" className="bg-accent px-2.5 py-1.5 text-2xl font-extrabold text-on-accent">{minute}</span>
          <span>{score.away}</span>
        </div>
        <div className="flex items-center justify-end gap-3.5 font-bold">
          <span className="hidden sm:inline">{m.away.name}</span>
          <Monogram club={m.away} solid />
        </div>
      </header>

      <div className="my-4 flex flex-wrap items-center justify-between gap-3">
        <PersonaBar clubName={clubName} playerName={playerName} />
        <div className="flex gap-4 text-sm">
          <Link to={`/match/${id}/best-plays`} className="font-bold text-text-on-bg">{t("best.tab")}</Link>
          <Link to="/matches" className="text-text-on-bg">{t("match.all")}</Link>
          <button type="button" onClick={() => setAbout(true)} className="border-0 bg-transparent p-0 text-sm text-text-on-bg underline">
            {t("match.about")}
          </button>
        </div>
      </div>

      {about && (
        <RealismPanel
          realism={m.realism}
          clubs={{ [m.home.club_id]: m.home.name, [m.away.club_id]: m.away.name }}
          onClose={() => setAbout(false)}
        />
      )}

      <div className="grid items-start gap-5 md:grid-cols-[7fr_5fr]">
        <section aria-label={t("what.match")}>
          <div role="tablist" aria-label={t("match.view")} className="flex gap-0.5">
            {TABS.map((name) => (
              <button
                key={name}
                role="tab"
                id={`tab-${name}`}
                aria-selected={tab === name}
                aria-controls="tab-panel"
                tabIndex={tab === name ? 0 : -1}
                onClick={() => setTab(name)}
                onKeyDown={(e) => {
                  const i = TABS.indexOf(tab);
                  if (e.key === "ArrowRight") setTab(TABS[(i + 1) % TABS.length]);
                  if (e.key === "ArrowLeft") setTab(TABS[(i + TABS.length - 1) % TABS.length]);
                }}
                className={`border-0 px-4 py-3 text-sm font-bold ${tab === name ? "bg-surface text-text" : "bg-black/30 text-text-on-bg"}`}
              >
                {t(`tab.${name}`)}
              </button>
            ))}
          </div>
          <div id="tab-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} className="bg-surface p-3.5 text-text">
          {tab === "team" && <TeamTab matchId={id} home={m.home} away={m.away} period={live.period} t={live.t} />}
          {tab === "player" && (
            <PlayerTab matchId={id} players={squad} playerId={useStore.getState().prefs.favorite_player_id ?? m.home_squad[9]?.player_id ?? squad[0].player_id} period={live.period} t={live.t} />
          )}
          <div hidden={tab !== "game"}>
          <Pitch colors={colors} label={t("match.pitch", { minute })} heat={heat}>
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
            {t("match.heat")}
          </label>
          </div>
          {live.connection === "reconnecting" && <p role="status" className="mt-2 text-sm text-warn">{t("match.reconnecting")}</p>}
          </div>
        </section>
        <aside aria-label={t("what.pundit")} className="order-first md:order-none">
          {live.ended ? (
            <RecapPanel matchId={id} lang={lang} />
          ) : rows.status === "ready" ? (
            <InsightPanel
              rows={rows.data}
              moments={momentById}
              period={live.period}
              t={live.t}
              addedS={m.added_time_s}
              onAskWhy={setAsking}
              onBestPlay={(row) => navigate(`/match/${id}/best-plays?insight=${row.insight.insight_id}`)}
            />
          ) : rows.status === "error" ? (
            <LoadError what="what.insights" retry={rows.retry} />
          ) : (
            <div className="bg-surface p-6 text-text"><Loading what="what.pundit" /></div>
          )}
        </aside>
      </div>

      {asking && (
        <div className="mt-5">
          <AskWhyPanel row={asking} matchId={id} variant={ready ?? { persona: "casual" }} lang={lang} addedS={m.added_time_s} names={names} onClose={() => setAsking(null)} />
        </div>
      )}

      <div className="mt-5">
        <StatsStrip matchId={id} homeId={m.home.club_id} awayId={m.away.club_id} period={live.period} t={live.t} />
      </div>
      <section aria-label={t("match.flow")} className="mt-0.5 bg-surface px-4 pb-4 pt-3 text-text">
        <Timeline moments={moments} firstHalfS={firstHalfS} totalS={totalS} period={live.period} t={live.t} addedS={m.added_time_s} onSeek={live.seek} />
        {timeline.status === "ready" && (
          <MomentumChart points={timeline.data.momentum} firstHalfS={firstHalfS} totalS={totalS} period={live.period} t={live.t} homeName={m.home.name} awayName={m.away.name} />
        )}
      </section>
    </main>
  );
}
