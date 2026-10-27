import type { InsightRow, Why } from "../../src/api/types";

export const ROW: InsightRow = {
  insight: {
    insight_id: "m1-m005-ins", moment_id: "m1-m005", match_id: "m1", level: "player",
    headline: "Morejo shines with a hat-trick", why: "w", recommendation: "r",
    claims: [{ text: "xG of 0.777", metric: "xg", value: 0.777, unit: "xG", ref: "metric:xg@2:2319.5/player:ach-09" }],
    event_ids: ["m1-e01200"], confidence: "high", verified: true, source: "agent", trace_id: "t-abc", prompt_version: "explainer.v1",
  },
  text: {
    insight_id: "m1-m005-ins", persona: "club_fan", lang: "en", headline: "Morejo shines with a hat-trick for Chapinero",
    body: "Harold Morejo's third goal at 84 minutes shows his sharpness.", verified: true,
    club_id: "chapinero", player_id: null, dir: "ltr", source: "agent",
  },
  best_play_event_id: "m1-e01200",
}; // prettier-ignore

export const WHY: Why = {
  claims: ROW.insight.claims,
  events: [{ event_id: "m1-e01200", match_id: "m1", period: 2, t: 2319.5, type: "shot", team_id: "chapinero", player_id: "ach-09",
             x: 95, y: 30, end_x: 105, end_y: 34, outcome: true, receiver_id: null, extras: {} }],
  agent_runs: [{ run_id: "r1", agent: "explainer", moment_id: "m1-m005", status: "ok", attempts: 1, latency_ms: 4200,
                 trace_id: "t-abc", error: null, tokens_in: 9000, tokens_out: 300 }],
  trace_id: "t-abc",
  counterfactual: {
    event_id: "m1-e01200",
    chosen: { kind: "shot", target_player_id: null, end: [105, 34], score: 0.31, pc_prob: 0.4, xt_gain: 0.2 },
    best: { kind: "pass", target_player_id: "ach-17", end: [99, 40], score: 0.42, pc_prob: 0.7, xt_gain: 0.33 },
    gain: 0.11,
    alternatives: [],
  },
}; // prettier-ignore
