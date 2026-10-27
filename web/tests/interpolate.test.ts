import { describe, expect, it } from "vitest";

import type { Frame } from "../src/api/types";
import { clockOf, fromClock, interpolate } from "../src/live/interpolate";

const frame = (t: number, players: [string, number, number][], ball: [number, number, number] = [50, 34, 0]): Frame => ({
  frame: Math.round(t * 10),
  period: 1,
  t,
  ball,
  players: players.map(([player_id, x, y]) => ({ player_id, team_id: "h", x, y })),
});

describe("interpolate", () => {
  it("moves players and the ball linearly between two frames", () => {
    const a = frame(10.0, [["p1", 10, 20]], [50, 34, 0]);
    const b = frame(10.2, [["p1", 12, 22]], [52, 34, 1]);
    const mid = interpolate(a, b, 10.1);
    expect(mid.players[0].x).toBeCloseTo(11);
    expect(mid.players[0].y).toBeCloseTo(21);
    expect(mid.ball[0]).toBeCloseTo(51);
    expect(mid.ball[2]).toBeCloseTo(0.5);
    expect(mid.t).toBeCloseTo(10.1);
  });

  it("keeps a player who is missing from the next frame where they were", () => {
    const a = frame(10.0, [["p1", 10, 20], ["off", 50, 50]]);
    const b = frame(10.2, [["p1", 12, 22]]); // "off" was sent off
    const mid = interpolate(a, b, 10.1);
    expect(mid.players.find((p) => p.player_id === "off")).toMatchObject({ x: 50, y: 50 });
  });

  it("clamps outside the two frames", () => {
    const a = frame(10.0, [["p1", 10, 20]]);
    const b = frame(10.2, [["p1", 12, 22]]);
    expect(interpolate(a, b, 9).players[0].x).toBe(10);
    expect(interpolate(a, b, 11).players[0].x).toBe(12);
  });
});

describe("match clock", () => {
  it("runs on through half time and back", () => {
    const firstHalf = 47 * 60; // 45 minutes plus 2 added
    expect(clockOf(1, 600, firstHalf)).toBe(600);
    expect(clockOf(2, 60, firstHalf)).toBe(firstHalf + 60);
    expect(fromClock(firstHalf + 60, firstHalf)).toEqual({ period: 2, t: 60 });
    expect(fromClock(600, firstHalf)).toEqual({ period: 1, t: 600 });
  });
});
