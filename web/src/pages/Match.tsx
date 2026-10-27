import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { MatchDetail } from "../api/types";
import RealismPanel from "../components/RealismPanel";
import { LoadError, Loading } from "../components/Status";
import { useAsync } from "../lib/useAsync";

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
  const [about, setAbout] = useState(false);

  if (state.status === "loading") return <main className="px-7"><Loading what="the match" /></main>;
  if (state.status === "error") return <main className="px-7 py-8"><LoadError what="the match" retry={state.retry} /></main>;
  const m = state.data;

  return (
    <main className="mx-auto max-w-[1280px] px-4 pb-10 pt-5 md:px-7">
      <header aria-label="Score" className="grid grid-cols-[1fr_auto_1fr] items-center gap-6">
        <div className="flex items-center gap-3.5 font-bold">
          <Monogram club={m.home} />
          <span className="hidden sm:inline">{m.home.name}</span>
        </div>
        <div className="font-display text-6xl font-black leading-none tabular-nums md:text-7xl">
          {m.score.home}–{m.score.away}
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
        <section aria-label="Match" className="bg-surface p-3.5 text-text" data-slot="pitch" />
        <aside aria-label="Your pundit" className="order-first bg-surface p-6 text-text md:order-none" data-slot="pundit" />
      </div>
    </main>
  );
}
