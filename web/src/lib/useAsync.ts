import { useCallback, useEffect, useState } from "react";

export type AsyncState<T> =
  | { status: "loading" }
  | { status: "error"; error: unknown; retry: () => void }
  | { status: "ready"; data: T };

/** Load data for a component, with loading and error states and a retry. ``deps`` re-run it. */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let live = true;
    setState({ status: "loading" });
    load().then(
      (data) => live && setState({ status: "ready", data }),
      (error: unknown) => live && setState({ status: "error", error, retry }),
    );
    return () => {
      live = false;
    };
  }, [...deps, attempt]);

  return state;
}
