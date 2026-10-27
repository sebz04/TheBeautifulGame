import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { openLive, type LiveHandlers } from "../src/live/stream";

/** A stand-in for the browser's EventSource that tests drive by hand. */
class FakeEventSource {
  static last: FakeEventSource;
  readyState = 0;
  closed = false;
  onerror: (() => void) | null = null;
  onopen: (() => void) | null = null;
  private listeners = new Map<string, ((e: MessageEvent) => void)[]>();

  constructor(readonly url: string) {
    FakeEventSource.last = this;
  }

  addEventListener(type: string, fn: (e: MessageEvent) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }

  close(): void {
    this.closed = true;
    this.readyState = 2;
  }

  emit(type: string, id: string, data: unknown): void {
    const e = new MessageEvent(type, { data: JSON.stringify(data), lastEventId: id });
    for (const fn of this.listeners.get(type) ?? []) fn(e);
  }
}

function handlers(): LiveHandlers & { calls: Record<string, unknown[]> } {
  const calls: Record<string, unknown[]> = { frame: [], event: [], cue: [], insight: [], end: [], status: [] };
  const rec = (k: string) => (x?: unknown) => void calls[k].push(x);
  return { calls, frame: rec("frame"), event: rec("event"), cue: rec("cue"), insight: rec("insight"), end: rec("end"), status: rec("status") };
}

beforeEach(() => vi.stubGlobal("EventSource", FakeEventSource));
afterEach(() => vi.unstubAllGlobals());

const frame = (t: number) => ({ frame: t * 10, period: 1, t, ball: [0, 0, 0], players: [] });

describe("openLive", () => {
  it("opens the stream at the requested position and speed", () => {
    openLive("m1", { period: 2, from_t: 120, speed: 2 }, handlers());
    expect(FakeEventSource.last.url).toBe("/api/matches/m1/live?period=2&from_t=120&speed=2");
  });

  it("ignores a message whose seq it has already seen", () => {
    const h = handlers();
    openLive("m1", { period: 1, from_t: 0, speed: 1 }, h);
    const es = FakeEventSource.last;
    es.emit("frame", "1:0.0:0", frame(0));
    es.emit("frame", "1:0.2:5", frame(0.2));
    es.emit("frame", "1:0.2:5", frame(0.2)); // replayed after a reconnect
    es.emit("frame", "1:0.0:3", frame(0)); // older
    expect(h.calls.frame).toHaveLength(2);
  });

  it("dedupes by seq and insight_id", () => {
    const seen = new Set<string>();
    const first = handlers();
    openLive("m1", { period: 1, from_t: 0, speed: 1 }, first, seen);
    FakeEventSource.last.emit("insight", "1:300.0:900", { insight_id: "i1", headline: "h" });
    // The viewer seeks back: a new stream, lower seqs are fine, but i1 isn't delivered twice.
    const second = handlers();
    openLive("m1", { period: 1, from_t: 100, speed: 1 }, second, seen);
    FakeEventSource.last.emit("frame", "1:100.0:400", frame(100));
    FakeEventSource.last.emit("insight", "1:300.0:900", { insight_id: "i1", headline: "h" });
    FakeEventSource.last.emit("insight", "1:400.0:1300", { insight_id: "i2", headline: "h2" });
    expect(first.calls.insight).toHaveLength(1);
    expect(second.calls.frame).toHaveLength(1);
    expect(second.calls.insight).toEqual([{ insight_id: "i2", headline: "h2" }]);
  });

  it("calls end and closes on the end message", () => {
    const h = handlers();
    openLive("m1", { period: 1, from_t: 0, speed: 1 }, h);
    FakeEventSource.last.emit("end", "2:2900.0:9999", { match_id: "m1" });
    expect(h.calls.end).toHaveLength(1);
    expect(FakeEventSource.last.closed).toBe(true);
  });

  it("reports reconnecting; closing it ourselves is not reported as a failure", () => {
    const h = handlers();
    const live = openLive("m1", { period: 1, from_t: 0, speed: 1 }, h);
    FakeEventSource.last.onerror?.();
    expect(h.calls.status).toEqual(["reconnecting"]);
    live.close();
    expect(FakeEventSource.last.closed).toBe(true);
    expect(h.calls.status).toEqual(["reconnecting"]);
  });

  it("reports closed once when the browser gives up", () => {
    const h = handlers();
    openLive("m1", { period: 1, from_t: 0, speed: 1 }, h);
    FakeEventSource.last.readyState = 2;
    FakeEventSource.last.onerror?.();
    FakeEventSource.last.onerror?.();
    expect(h.calls.status).toEqual(["closed"]);
  });
});
