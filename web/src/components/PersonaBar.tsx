// The fan's view: two two-position switches (Team ⇄ Player, Fan ⇄ Scout) and a language
// menu. Each switch is a pair of buttons with aria-pressed, so it reads and works the same
// by mouse, keyboard, and screen reader.
import type { Lang } from "../api/types";
import { LANG_NAMES, useT } from "../i18n/i18n";
import type { Focus, Mode } from "../state/prefs";
import { useStore } from "../state/store";

function Switch<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; text: string; disabled?: boolean }[];
  onChange: (v: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-full border-[1.5px] border-white/55 bg-deep p-[3px]">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
          className={`rounded-full border-0 px-4 py-2 text-sm font-bold transition-colors duration-[var(--mm-dur-fast)] disabled:cursor-not-allowed disabled:opacity-50 ${
            value === o.value ? "bg-accent text-on-accent" : "bg-transparent text-text-on-deep"
          }`}
        >
          {o.text}
        </button>
      ))}
    </div>
  );
}

export default function PersonaBar({ clubName, playerName }: { clubName: string | null; playerName: string | null }) {
  const t = useT();
  const prefs = useStore((s) => s.prefs);
  const setPrefs = useStore((s) => s.setPrefs);
  return (
    <nav aria-label={t("bar.view")} className="flex flex-wrap items-center gap-3">
      <Switch<Focus>
        label={t("bar.follow")}
        value={prefs.focus}
        onChange={(focus) => setPrefs({ focus })}
        options={[
          { value: "team", text: clubName ?? t("bar.team") },
          { value: "player", text: playerName ?? t("bar.player"), disabled: !playerName },
        ]}
      />
      <Switch<Mode>
        label={t("bar.mode")}
        value={prefs.mode}
        onChange={(mode) => setPrefs({ mode })}
        options={[
          { value: "fan", text: t("bar.fan") },
          { value: "scout", text: t("bar.scout") },
        ]}
      />
      <label className="flex items-center">
        <span className="sr-only">{t("bar.language")}</span>
        <select
          value={prefs.lang}
          onChange={(e) => setPrefs({ lang: e.target.value as Lang })}
          className="rounded-full border-[1.5px] border-white/55 bg-transparent px-3.5 py-2.5 text-sm text-text-on-bg"
        >
          {(Object.keys(LANG_NAMES) as Lang[]).map((l) => (
            <option key={l} value={l} lang={l} className="text-[#16161C]">
              {LANG_NAMES[l]}
            </option>
          ))}
        </select>
      </label>
    </nav>
  );
}
