// "Ask why": the evidence behind an insight (claims, cited events, the agents' runs and
// trace), the best alternative to the cited decision, and a live re-ask of the pundit.
import { useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import type { AgentRun, Counterfactual, InsightRow, Lang, Persona, Regenerated, Why } from "../api/types";
import { useT } from "../i18n/i18n";
import { optionLine, type T } from "../lib/options";
import { useAsync } from "../lib/useAsync";
import { minuteLabel } from "../live/minute";
import { LoadError, Loading } from "./Status";

export interface Variant {
  persona: Persona;
  club_id?: string;
  player_id?: string;
}

/** A small pitch with the real choice dashed and the best option as an arrow. */
export function CounterfactualPitch({ cf, from, label }: { cf: Counterfactual; from: [number, number]; label: string }) {
  const p = ([x, y]: [number, number]) => [x * 3, (68 - y) * 3] as const;
  const [ox, oy] = p(from);
  const [cx, cy] = p(cf.chosen.end);
  const [bx, by] = p(cf.best.end);
  return (
    <svg viewBox="0 0 315 204" role="img" aria-label={label} className="block h-auto w-full bg-[color:var(--mm-pitch)]">
      <defs>
        <marker id="mm-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="var(--mm-accent)" />
        </marker>
      </defs>
      <g fill="none" stroke="var(--mm-pitch-line)" strokeWidth="1.5">
        <rect x="1" y="1" width="313" height="202" />
        <line x1="157.5" y1="1" x2="157.5" y2="203" />
        <rect x="1" y="41" width="49" height="121" />
        <rect x="265" y="41" width="49" height="121" />
      </g>
      <line x1={ox} y1={oy} x2={cx} y2={cy} stroke="var(--mm-muted)" strokeWidth="3" strokeDasharray="6 5" />
      <line x1={ox} y1={oy} x2={bx} y2={by} stroke="var(--mm-accent)" strokeWidth="4" markerEnd="url(#mm-arrow)" />
      <circle cx={ox} cy={oy} r="6" fill="var(--mm-home)" stroke="#fff" strokeWidth="2" />
    </svg>
  );
}

/** Agent runs grouped by agent: "explainer: 3 runs, 38.1 s" (fallbacks to templates counted). */
export function runSummary(runs: AgentRun[]): string[] {
  const by = new Map<string, { n: number; ms: number; retries: number }>();
  for (const r of runs) {
    const name = r.agent.startsWith("template:") ? `template (${r.agent.slice(9)})` : r.agent;
    const g = by.get(name) ?? { n: 0, ms: 0, retries: 0 };
    by.set(name, { n: g.n + 1, ms: g.ms + r.latency_ms, retries: g.retries + Math.max(0, r.attempts - 1) });
  }
  return [...by].map(([name, g]) =>
    name.startsWith("template")
      ? `${name}: used ${g.n} time${g.n === 1 ? "" : "s"}`
      : `${name}: ${g.n} run${g.n === 1 ? "" : "s"}, ${(g.ms / 1000).toFixed(1)} s${g.retries ? `, ${g.retries} retr${g.retries === 1 ? "y" : "ies"}` : ""}`,
  );
}

/** Where the cited decision was made (the counterfactual's event). */
function decisionOf(why: Why): [number, number] | null {
  const e = why.events.find((x) => x.event_id === why.counterfactual?.event_id);
  return e ? [e.x, e.y] : null;
}

function liveError(e: unknown, t: T): string {
  if (e instanceof ApiError && e.status === 429) {
    return t("live.limit", { minutes: Math.max(1, Math.ceil((e.retry_after ?? 60) / 60)) });
  }
  if (e instanceof ApiError && e.status === 504) return t("live.timeout");
  return t("live.down");
}

export interface AskWhyPanelProps {
  row: InsightRow;
  matchId: string;
  variant: Variant;
  lang: Lang;
  addedS: [number, number];
  names: Record<string, string>;
  onClose: () => void;
}

export default function AskWhyPanel({ row, matchId, variant, lang, addedS, names, onClose }: AskWhyPanelProps) {
  const t = useT();
  const why = useAsync(() => api.why(row.insight.insight_id), [row.insight.insight_id]);
  const [live, setLive] = useState<{ state: "idle" | "running" } | { state: "done"; result: Regenerated } | { state: "error"; message: string }>({ state: "idle" });
  const running = useRef(false);

  const askLive = () => {
    if (running.current) return;
    running.current = true;
    setLive({ state: "running" });
    api
      .regenerate(matchId, { moment_id: row.insight.moment_id, persona: variant.persona, lang, ...(variant.club_id ? { club_id: variant.club_id } : {}), ...(variant.player_id ? { player_id: variant.player_id } : {}) })
      .then(
        (result) => setLive({ state: "done", result }),
        (e: unknown) => setLive({ state: "error", message: liveError(e, t) }),
      )
      .finally(() => (running.current = false));
  };

  return (
    <section aria-labelledby="why-title" className="bg-surface p-6 text-text" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <div className="flex items-start justify-between gap-4">
        <h2 id="why-title" className="m-0 font-display text-3xl font-extrabold">
          {t("why.title")}
        </h2>
        <button type="button" onClick={onClose} className="border border-text bg-transparent px-3 py-2 text-text">
          {t("close")}
        </button>
      </div>

      {why.status === "loading" && <Loading what="what.evidence" />}
      {why.status === "error" && <LoadError what="what.evidence" retry={why.retry} />}
      {why.status === "ready" && (
        <div className="mt-4 grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="mb-2 mt-0 text-sm font-bold text-muted">{t("why.numbers")}</h3>
            <ul className="m-0 list-none p-0">
              {why.data.claims.map((c) => (
                <li key={c.ref} className="border-t border-[color:var(--mm-rule)] py-2">
                  <span>{c.text}</span>
                </li>
              ))}
            </ul>
            <h3 className="mb-2 mt-5 text-sm font-bold text-muted">{t("why.moments")}</h3>
            <ul className="m-0 list-none p-0">
              {why.data.events.map((e) => (
                <li key={e.event_id} className="border-t border-[color:var(--mm-rule)] py-2">
                  <b className="font-display text-lg">{minuteLabel(e.period, e.t, addedS)}</b> {e.type}
                  {e.player_id && names[e.player_id] ? `, ${names[e.player_id]}` : ""}
                </li>
              ))}
            </ul>
            <h3 className="mb-2 mt-5 text-sm font-bold text-muted">{t("why.agents")}</h3>
            <ul className="m-0 list-none p-0 text-sm">
              {runSummary(why.data.agent_runs).map((line) => (
                <li key={line} className="border-t border-[color:var(--mm-rule)] py-2">
                  {line}
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted">{why.data.trace_id ? t("why.trace", { id: why.data.trace_id }) : t("why.traceNone")}</p>
          </div>
          <div>
            {why.data.counterfactual && decisionOf(why.data) && (
              <>
                <h3 className="mb-2 mt-0 text-sm font-bold text-muted">{t("why.else")}</h3>
                <CounterfactualPitch cf={why.data.counterfactual} from={decisionOf(why.data)!} label={t("why.pitch")} />
                <p className="mb-1 mt-2 text-sm text-muted">{t("why.happened", { option: optionLine(why.data.counterfactual.chosen, names, t) })}</p>
                <p className="m-0 text-sm">{t("why.best", { option: optionLine(why.data.counterfactual.best, names, t) })}</p>
              </>
            )}
            <div className="mt-6 border-t border-[color:var(--mm-rule)] pt-4">
              <button type="button" onClick={askLive} disabled={live.state === "running"} className="border-0 bg-accent px-4 py-2.5 font-bold text-on-accent disabled:opacity-60">
                {t("live.ask")}
              </button>
              <p className="mb-0 mt-2 text-xs text-muted">{t("live.hint")}</p>
              {live.state === "running" && (
                <p role="status" className="mt-3 text-sm">
                  {t("live.working")}
                </p>
              )}
              {live.state === "error" && (
                <p role="alert" className="mt-3 text-sm text-warn">
                  {live.message}
                </p>
              )}
              <div className={`mt-4 grid gap-4 ${live.state === "done" ? "sm:grid-cols-2" : ""}`}>
                <article lang={row.text.lang} dir={row.text.dir} className="border-l-4 border-[color:var(--mm-rule)] pl-4">
                  <p className="m-0 text-xs text-muted">{t("why.checked")}</p>
                  <h3 className="mb-0 mt-1 font-display text-2xl font-extrabold">{row.text.headline}</h3>
                  <p className="my-2 text-sm">{row.text.body}</p>
                </article>
              {live.state === "done" && (
                <article lang={live.result.text.lang} dir={live.result.text.dir} className="border-l-4 border-accent pl-4">
                  <p className="m-0 text-xs text-muted">{t("why.justNow")}</p>
                  <h3 className="m-0 font-display text-2xl font-extrabold">{live.result.text.headline}</h3>
                  <p className="my-2">{live.result.text.body}</p>
                  <p className="m-0 text-xs text-muted">
                    {live.result.agent_runs.map((r) => r.agent).join(", ")}. {live.result.trace_id ? t("why.trace", { id: live.result.trace_id }) : ""}
                  </p>
                </article>
              )}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
