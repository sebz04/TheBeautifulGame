// The live replay stream (SSE). The browser's EventSource reconnects by itself and sends
// Last-Event-ID, so the server resumes after the last message; we still drop anything at or
// below the last seq seen on this stream, and deliver each insight once per session (a seek
// opens a new stream, and seeking back must not repeat insight cards).
import type { Cue, Frame, LiveInsight, MatchEvent, Period } from "../api/types";

export type LiveStatus = "open" | "reconnecting" | "closed";

export interface LiveHandlers {
  frame: (f: Frame) => void;
  event: (e: MatchEvent) => void;
  cue: (c: Cue) => void;
  insight: (i: LiveInsight) => void;
  end: () => void;
  status: (s: LiveStatus) => void;
}

export interface LiveOptions {
  period: Period;
  from_t: number;
  speed: number;
}

export interface LiveHandle {
  close(): void;
}

const seqOf = (id: string): number => Number(id.slice(id.lastIndexOf(":") + 1));

export function openLive(
  matchId: string,
  opts: LiveOptions,
  handlers: LiveHandlers,
  seenInsights: Set<string> = new Set(),
): LiveHandle {
  const url = `/api/matches/${matchId}/live?period=${opts.period}&from_t=${opts.from_t}&speed=${opts.speed}`;
  const es = new EventSource(url);
  let lastSeq = -1;
  let closed = false;

  const close = () => {
    if (closed) return;
    closed = true;
    es.close();
    handlers.status("closed");
  };

  const on = <T>(type: string, deliver: (data: T) => void) =>
    es.addEventListener(type, (e: MessageEvent) => {
      const seq = seqOf(e.lastEventId);
      if (!Number.isFinite(seq) || seq <= lastSeq) return;
      lastSeq = seq;
      deliver(JSON.parse(e.data) as T);
    });

  on<Frame>("frame", handlers.frame);
  on<MatchEvent>("event", handlers.event);
  on<Cue>("cue", handlers.cue);
  on<LiveInsight>("insight", (i) => {
    if (seenInsights.has(i.insight_id)) return;
    seenInsights.add(i.insight_id);
    handlers.insight(i);
  });
  on<unknown>("end", () => {
    handlers.end();
    close();
  });
  es.onopen = () => handlers.status("open");
  es.onerror = () => {
    if (!closed) handlers.status(es.readyState === 2 ? "closed" : "reconnecting");
  };
  return { close };
}
