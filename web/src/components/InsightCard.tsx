// The pundit's newest insight, written for this fan: the loudest thing on the page. A scout
// (the analyst voice) also gets the verified numbers behind it and the tactical advice; a fan
// gets the story alone.
import type { InsightRow } from "../api/types";
import { useT } from "../i18n/i18n";

export interface InsightCardProps {
  row: InsightRow;
  minute: string;
  onAskWhy: () => void;
  onBestPlay: (eventId: string) => void;
}

export default function InsightCard({ row, minute, onAskWhy, onBestPlay }: InsightCardProps) {
  const t = useT();
  const { text, insight, best_play_event_id } = row;
  return (
    <article
      lang={text.lang}
      dir={text.dir}
      className="animate-rise border-t-[6px] border-accent bg-surface px-6 pb-5 pt-6 text-text"
    >
      <div dir="ltr" className="font-display text-5xl font-black leading-none text-accent [text-align:start]">{minute}</div>
      <h2 className="mb-3.5 mt-4 font-display text-[2.6rem] font-extrabold leading-[0.98]">{text.headline}</h2>
      <p className="mb-5 mt-0 max-w-[46ch] text-base">{text.body}</p>
      {text.persona === "analyst" && text.source === "agent" && insight.claims.length > 0 && (
        <section className="mb-5">
          <h3 className="mb-1.5 mt-0 text-xs font-bold uppercase tracking-wide text-muted">{t("card.numbers")}</h3>
          <ul className="m-0 list-none p-0 text-sm">
            {insight.claims.map((c) => (
              <li key={c.ref + c.metric} dir="ltr" className="border-t border-[color:var(--mm-rule)] py-1.5 [text-align:start]">
                {c.text}
              </li>
            ))}
          </ul>
          {text.lang === "en" && insight.recommendation && (
            <>
              <h3 className="mb-1.5 mt-4 text-xs font-bold uppercase tracking-wide text-muted">{t("card.advice")}</h3>
              <p className="m-0 max-w-[46ch] text-sm">{insight.recommendation}</p>
            </>
          )}
        </section>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={onAskWhy} className="border-[1.5px] border-accent bg-accent px-3.5 py-2.5 text-sm font-bold text-on-accent">
          {t("card.askWhy")}
        </button>
        {best_play_event_id && (
          <button
            type="button"
            onClick={() => onBestPlay(best_play_event_id)}
            className="border-[1.5px] border-text bg-transparent px-3.5 py-2.5 text-sm font-bold text-text"
          >
            {t("card.bestPlay")}
          </button>
        )}
      </div>
      <p className="mb-0 mt-3.5 text-xs text-muted">
        {t("card.confidence", { level: t(`level.${insight.confidence}`) })}
        {text.source === "template" && ` ${t("card.template")}`}
      </p>
    </article>
  );
}
