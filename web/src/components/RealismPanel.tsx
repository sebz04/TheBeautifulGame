import type { MatchDetail } from "../api/types";

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
          About this match
        </h2>
        <button type="button" onClick={onClose} className="border border-text bg-transparent px-3 py-2 text-text" autoFocus>
          Close
        </button>
      </div>
      <p className="max-w-prose text-muted">
        This match is synthetic: a simulation engine played it, and the stats are checked against the ranges of real
        professional football. It passes {passed.length} of {realism.checks.length} checks. A single match often lands
        outside a range or two, the way a real match can; across many simulated matches, every check passes.
      </p>
      <ul className="m-0 grid list-none gap-1 p-0 sm:grid-cols-2">
        {[...missed, ...passed].map((c) => (
          <li key={c.name} className="flex justify-between gap-3 border-t border-[color:var(--mm-rule)] py-2 text-sm">
            <span>{checkLabel(c.name, clubs)}</span>
            <span className={`tabular-nums ${c.ok ? "text-good" : "text-warn"}`}>
              {c.ok ? "in range" : "outside"} ({Number(c.value.toFixed(2))}; {c.lo}–{c.hi})
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
