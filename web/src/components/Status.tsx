// Shared loading and error states: say what is happening and how to fix it.
import { useT, type Key } from "../i18n/i18n";

export function Loading({ what }: { what: Key }) {
  const t = useT();
  return (
    <p role="status" className="py-8 text-text-on-bg">
      {t("loading", { what: t(what) })}
    </p>
  );
}

export function LoadError({ what, retry }: { what: Key; retry: () => void }) {
  const t = useT();
  return (
    <div role="alert" className="bg-surface p-5 text-text">
      <p className="m-0 mb-3">{t("loadError", { what: t(what) })}</p>
      <button
        type="button"
        onClick={retry}
        className="border-0 bg-accent px-4 py-2.5 font-bold text-on-accent"
      >
        {t("tryAgain")}
      </button>
    </div>
  );
}
