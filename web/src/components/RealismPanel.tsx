import type { MatchDetail } from "../api/types";
import { useT } from "../i18n/i18n";

/** "throw_ins:laureles" → "Throw ins, Atlético Laureles" */
export function checkLabel(name: string, clubs: Record<string, string>): string {
  const [metric, club] = name.split(":");
  const words = metric.replace(/_/g, " ");
  const label = words.charAt(0).toUpperCase() + words.slice(1);
  return club ? `${label}, ${clubs[club] ?? club}` : label;
}

/** "About this match": the synthetic data's realism checks, explained plainly. */
export default function RealismPanel({
  realism,
  clubs,
  onClose,
}: {
  realism: MatchDetail["realism"];
  clubs: Record<string, string>;
  onClose: () => void;
}) {
  const t = useT();
  const passed = realism.checks.filter((c) => c.ok);
  const missed = realism.checks.filter((c) => !c.ok);
  return (
    <section
      role="dialog"
      aria-labelledby="realism-title"
      className="bg-surface p-6 text-text"
      onKeyDown={(e) => e.key === "Escape" && onClose()}
    >
      <div className="flex items-start justify-between gap-4">
        <h2 id="realism-title" className="m-0 font-display text-3xl font-extrabold">
          {t("match.about")}
        </h2>
        <button type="button" onClick={onClose} className="border border-text bg-transparent px-3 py-2 text-text" autoFocus>
          {t("close")}
        </button>
      </div>
      <p className="max-w-prose text-muted">
        {t("realism.intro", { passed: passed.length, total: realism.checks.length })}
      </p>
      <ul className="m-0 grid list-none gap-1 p-0 sm:grid-cols-2">
        {[...missed, ...passed].map((c) => (
          <li key={c.name} className="flex justify-between gap-3 border-t border-[color:var(--mm-rule)] py-2 text-sm">
            <span>{checkLabel(c.name, clubs)}</span>
            <span className={`tabular-nums ${c.ok ? "text-good" : "text-warn"}`}>
              {c.ok ? t("realism.in") : t("realism.out")} ({Number(c.value.toFixed(2))}; {c.lo}–{c.hi})
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
