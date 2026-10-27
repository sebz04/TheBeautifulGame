// At the final whistle the full-time recap takes over the pundit's column.
import { api } from "../api/client";
import type { Lang } from "../api/types";
import { useT } from "../i18n/i18n";
import { useAsync } from "../lib/useAsync";
import { LoadError, Loading } from "./Status";

export default function RecapPanel({ matchId, lang }: { matchId: string; lang: Lang }) {
  const t = useT();
  const state = useAsync(() => api.recap(matchId, lang), [matchId, lang]);
  if (state.status === "loading") return <div className="bg-surface p-6 text-text"><Loading what="what.recap" /></div>;
  if (state.status === "error") return <LoadError what="what.recap" retry={state.retry} />;
  const r = state.data;
  return (
    <article lang="en" dir="ltr" className="border-t-[6px] border-accent bg-surface px-6 pb-6 pt-6 text-text">
      <p className="m-0 text-sm text-muted">{t("recap.fullTime")}</p>
      <h2 className="mb-4 mt-2 font-display text-[2.6rem] font-extrabold leading-[0.98]">{r.title}</h2>
      {r.paragraphs.map((p) => (
        <p key={p} className="mb-3 mt-0 max-w-[52ch]">
          {p}
        </p>
      ))}
      {lang !== "en" && <p className="mb-0 mt-4 text-xs text-muted">{t("recap.english")}</p>}
    </article>
  );
}
