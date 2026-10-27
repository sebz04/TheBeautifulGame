import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { frameAt } from "../src/components/Pitch";
import { useStore, type ArrivedFrame } from "../src/state/store";

class FakeEventSource {
  static all: FakeEventSource[] = [];
  closed = false;
  readyState = 0;
  onerror = null;
  onopen = null;
  constructor(readonly url: string) {
    FakeEventSource.all.push(this);
  }
  addEventListener() {}
  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  FakeEventSource.all = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  useStore.setState({ matchId: null });
  useStore.getState().openMatch("m1");
});
afterEach(() => vi.unstubAllGlobals());

describe("live replay in the store", () => {
  it("starts paused at kickoff and opens the stream on play", () => {
    expect(FakeEventSource.all).toHaveLength(0);
    useStore.getState().play();
    expect(FakeEventSource.all[0].url).toBe("/api/matches/m1/live?period=1&from_t=0&speed=1");
  });

  it("seeking while playing reopens the stream at the new time", () => {
    useStore.getState().play();
    useStore.getState().seek(2, 90);
    expect(FakeEventSource.all[0].closed).toBe(true);
    expect(FakeEventSource.all[1].url).toBe("/api/matches/m1/live?period=2&from_t=90&speed=1");
  });

  it("seeking while paused only moves the clock", () => {
    useStore.getState().seek(1, 300);
    expect(FakeEventSource.all).toHaveLength(0);
    expect(useStore.getState().t).toBe(300);
    useStore.getState().play();
    expect(FakeEventSource.all[0].url).toContain("from_t=300");
  });

  it("changing speed reopens at the current time; pause closes", () => {
    useStore.getState().play();
    useStore.getState().setSpeed(4);
    expect(FakeEventSource.all[1].url).toContain("speed=4");
    useStore.getState().pause();
    expect(FakeEventSource.all[1].closed).toBe(true);
    expect(useStore.getState().playing).toBe(false);
  });
});

describe("frameAt", () => {
  const f = (t: number, arrived: number, x: number): ArrivedFrame => ({
    frame: t * 10, period: 1, t, ball: [0, 0, 0], arrived,
    players: [{ player_id: "p", team_id: "h", x, y: 0 }],
  }); // prettier-ignore

  it("draws one frame interval behind the newest, interpolated", () => {
    const frames = [f(10.0, 0, 10), f(10.2, 200, 12), f(10.4, 400, 14)];
    expect(frameAt(frames, 400, 1)!.players[0].x).toBeCloseTo(12); // t 10.2
    expect(frameAt(frames, 500, 1)!.players[0].x).toBeCloseTo(13); // 100 ms later: t 10.3
  });

  it("is null before any frame arrives", () => {
    expect(frameAt([], 0, 1)).toBeNull();
  });
});
