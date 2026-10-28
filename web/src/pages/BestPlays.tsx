// The Best Plays tab: decisions worth a second look, frozen and compared with the best
// option, while the live match keeps playing in the strip at the top.
import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { InsightRow, Moment, Period } from "../api/types";
import FreezeFrame from "../components/FreezeFrame";
import LiveStrip from "../components/LiveStrip";
import { LoadError, Loading } from "../components/Status";
import { useT } from "../i18n/i18n";
import { useAsync } from "../lib/useAsync";
import { useFanMatch } from "../lib/useFanMatch";
import { minuteLabel } from "../live/minute";
import { useStore } from "../state/store";
import { hasSubstance } from "../components/InsightPanel";

/** Insights with a best play whose moment has ended by (period, t), newest first. */
export function bestPlayMoments(rows: InsightRow[], moments: Record<string, Moment>, period: Period, t: number): InsightRow[] {
  return rows
    .filter(hasSubstance)
    .filter((r) => {
      const m = moments[r.insight.moment_id];
      return r.best_play_event_id && m && (m.period < period || (m.period === period && m.t_end <= t));
    })
    .sort((a, b) => {
      const [ma, mb] = [moments[a.insight.moment_id], moments[b.insight.moment_id]];
      return mb.period - ma.period || mb.t_end - ma.t_end;
    });
}

function Frozen({ matchId, row, names, colors, addedS }: { matchId: string; row: InsightRow; names: Record<string, string>; colors: { home: string; away: string; homeId: string }; addedS: [number, number] }) {
  const t = useT();
  const data = useAsync(async () => {
    const why = await api.why(row.insight.insight_id);
    const event = why.events.find((e) => e.event_id === (why.counterfactual?.event_id ?? row.best_play_event_id));
    if (!why.counterfactual || !event) return { why, event: null, frame: null, heat: null };
    const at = Math.round(event.t * 10) / 10;
    const [tracking, heat] = await Promise.all([
      api.tracking(matchId, event.period, Math.max(0, at - 0.2), at),
      api.pitchControl(matchId, event.period, at).catch(() => null),
    ]);
    return { why, event, frame: tracking.frames.at(-1) ?? null, heat };
  }, [matchId, row.insight.insight_id]);

  if (data.status === "loading") return <Loading what="what.evidence"  onCard />;
  if (data.status === "error") return <LoadError what="what.evidence" retry={data.retry} />;
  const { why, event, frame, heat } = data.data;
  if (!why.counterfactual || !event) return <p className="text-muted">{t("best.empty")}</p>;
  return (
    <div>
      <p className="m-0 mb-2 text-sm font-bold">{t("best.frozen", { minute: minuteLabel(event.period, event.t, addedS) })}</p>
      <FreezeFrame key={row.insight.insight_id} cf={why.counterfactual} from={[event.x, event.y]} frame={frame} heat={heat} colors={colors} names={names} />
      <article lang={row.text.lang} dir={row.text.dir} className="mt-4 border-s-4 border-accent ps-4">
        <p className="m-0 text-xs text-muted">{t("best.pundit")}</p>
        <h2 className="mb-1 mt-1 font-display text-2xl font-extrabold">{row.text.headline}</h2>
        <p className="m-0 text-sm">{row.text.body}</p>
      </article>
    </div>
  );
}

export default function BestPlays() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const t = useT();
  const fan = useFanMatch(id);
  const period = useStore((s) => s.period);
  const now = useStore((s) => s.t);
  const moments = useMemo(() => (fan.timeline.status === "ready" ? fan.timeline.data.moments : []), [fan.timeline]);
  const byId = useMemo(() => Object.fromEntries(moments.map((m) => [m.moment_id, m])), [moments]);

  if (fan.match.status === "loading") return <main className="px-7"><Loading what="what.match" /></main>;
  if (fan.match.status === "error") return <main className="px-7 py-8"><LoadError what="what.match" retry={fan.match.retry} /></main>;
  const m = fan.match.data;
  const names = Object.fromEntries([...m.home_squad, ...m.away_squad].map((p) => [p.player_id, p.name]));
  const colors = { home: m.home.primary_color, away: m.away.primary_color, homeId: m.home.club_id };
  const list = fan.rows.status === "ready" ? bestPlayMoments(fan.rows.data, byId, period, now) : [];
  const chosen = list.find((r) => r.insight.insight_id === params.get("insight")) ?? list[0];

  return (
    <main className="mx-auto max-w-[1280px] px-4 pb-10 pt-5 md:px-7" style={{ "--mm-home": m.home.primary_color, "--mm-away": m.away.primary_color } as React.CSSProperties}>
      <LiveStrip match={m} moments={moments} />
      <div className="my-4 flex flex-wrap items-baseline gap-4">
        <h1 className="m-0 font-display text-5xl font-black">{t("best.title")}</h1>
        <nav className="flex gap-0.5 text-sm font-bold">
          <Link to={`/match/${id}`} className="bg-deep px-4 py-2.5 text-text-on-deep">{t("best.live")}</Link>
          <span aria-current="page" className="bg-surface px-4 py-2.5 text-text">{t("best.tab")}</span>
        </nav>
      </div>
      <div className="grid items-start gap-5 md:grid-cols-[4fr_8fr]">
        <section className="bg-surface p-4 text-text">
          <h2 id="moments-title" className="m-0 mb-2 text-sm font-bold text-muted">{t("best.list")}</h2>
          {list.length === 0 ? (
            <p className="text-sm text-muted">{t("best.empty")}</p>
          ) : (
            <ul aria-labelledby="moments-title" className="m-0 list-none p-0">
              {list.map((r) => {
                const mo = byId[r.insight.moment_id];
                const active = r === chosen;
                return (
                  <li key={r.insight.insight_id}>
                    <button
                      type="button"
                      aria-current={active}
                      onClick={() => setParams({ insight: r.insight.insight_id })}
                      lang={r.text.lang}
                      dir={r.text.dir}
                      className={`grid w-full grid-cols-[3.2rem_1fr] gap-2 border-0 border-t border-[color:var(--mm-rule)] px-2 py-3 text-start text-sm ${active ? "bg-accent text-on-accent" : "bg-transparent text-text"}`}
                    >
                      <span dir="ltr" className="font-display text-xl font-extrabold [text-align:start]">{minuteLabel(mo.period, mo.t_end, m.added_time_s)}</span>
                      <span>{r.text.headline}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
        <section className="bg-surface p-4 text-text">
          {chosen ? <Frozen matchId={id} row={chosen} names={names} colors={colors} addedS={m.added_time_s} /> : <p className="text-muted">{t("best.empty")}</p>}
        </section>
      </div>
    </main>
  );
}
