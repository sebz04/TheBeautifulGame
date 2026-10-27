// Shared loading and error states: say what is happening and how to fix it.

export function Loading({ what }: { what: string }) {
  return (
    <p role="status" className="py-8 text-text-on-bg">
      Loading {what}…
    </p>
  );
}

export function LoadError({ what, retry }: { what: string; retry: () => void }) {
  return (
    <div role="alert" className="bg-surface p-5 text-text">
      <p className="m-0 mb-3">Couldn't load {what}. Check that the API is running, then try again.</p>
      <button
        type="button"
        onClick={retry}
        className="border-0 bg-accent px-4 py-2.5 font-bold text-on-accent"
      >
        Try again
      </button>
    </div>
  );
}
