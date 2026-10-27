// While the fan looks at a best play, the live match keeps going: clock, score, and a way back.
import { Link } from "react-router-dom";

import type { MatchDetail, Moment } from "../api/types";
import { useT } from "../i18n/i18n";
import { minuteLabel } from "../live/minute";
import { scoreAt } from "../live/score";
import { useStore } from "../state/store";

export default function LiveStrip({ match, moments }: { match: MatchDetail; moments: Moment[] }) {
  const t = useT();
  const period = useStore((s) => s.period);
  const now = useStore((s) => s.t);
  const playing = useStore((s) => s.playing);
  const score = scoreAt(moments, period, now, match.home.club_id);
  return (
    <section aria-label={t("best.live")} className="flex flex-wrap items-center gap-3 bg-deep px-4 py-2.5 text-sm text-text-on-deep">
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${playing ? "animate-pulse bg-[color:var(--mm-warn)]" : "bg-[color:var(--mm-muted)]"}`} aria-hidden="true" />
      <b>{t("best.live")}</b>
      <span dir="ltr" className="font-display text-xl font-extrabold">{minuteLabel(period, now, match.added_time_s)}</span>
      <span>
        {match.home.short} <b dir="ltr" className="font-display text-xl">{score.home}–{score.away}</b> {match.away.short}
      </span>
      <Link to={`/match/${match.match_id}`} className="ms-auto font-bold text-text-on-deep">
        {t("best.back")}
      </Link>
    </section>
  );
}
