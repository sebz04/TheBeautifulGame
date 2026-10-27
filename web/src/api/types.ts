// Mirrors the TASK-21 API exactly (wiki/api-frontend.md, src/matchmind/schemas.py).

export type Persona = "analyst" | "casual" | "club_fan" | "player_focus";
export type Lang = "en" | "es" | "pt" | "fr" | "ar";
export type Level = "game" | "team" | "player";
export type Period = 1 | 2;

export interface Club {
  club_id: string;
  name: string;
  short: string;
  primary_color: string;
  secondary_color: string;
  formation: string;
}

export interface Player {
  player_id: string;
  name: string;
  club_id: string;
  number: number;
  position: "GK" | "DF" | "MF" | "FW";
}

export interface Score {
  home: number;
  away: number;
}

export interface MatchRow {
  match_id: string;
  title: string;
  home: Club;
  away: Club;
  score: Score;
  scenario_id: string;
}

export interface RealismCheck {
  name: string;
  value: number;
  lo: number;
  hi: number;
  ok: boolean;
}

export interface MatchDetail {
  match_id: string;
  seed: number;
  home: Club;
  away: Club;
  home_squad: Player[];
  away_squad: Player[];
  scenario_id: string;
  stadium: string;
  kickoff_iso: string;
  added_time_s: [number, number];
  score: Score;
  realism: { checks: RealismCheck[]; ok: boolean };
}

export interface PlayerPos {
  player_id: string;
  team_id: string;
  x: number;
  y: number;
}

/** A frame as the live stream sends it (5 Hz). */
export interface Frame {
  frame: number;
  period: Period;
  t: number;
  ball: [number, number, number];
  players: PlayerPos[];
}

export interface MatchEvent {
  event_id: string;
  match_id: string;
  period: Period;
  t: number;
  type: string;
  team_id: string;
  player_id: string | null;
  x: number;
  y: number;
  end_x: number | null;
  end_y: number | null;
  outcome: boolean | null;
  receiver_id: string | null;
  extras: Record<string, unknown>;
}

export interface Moment {
  moment_id: string;
  match_id: string;
  period: Period;
  t_start: number;
  t_end: number;
  kind: string;
  level: Level;
  team_id: string | null;
  player_id: string | null;
  trigger_metric: string;
  trigger_value: number;
  event_ids: string[];
}

export interface MomentumPoint {
  period: Period;
  t: number;
  home: number;
  away: number;
  diff: number;
}

export interface Timeline {
  moments: Moment[];
  momentum: MomentumPoint[];
}

export interface Claim {
  text: string;
  metric: string;
  value: number;
  unit: string;
  ref: string;
}

export interface Insight {
  insight_id: string;
  moment_id: string;
  match_id: string;
  level: Level;
  headline: string;
  why: string;
  recommendation: string;
  claims: Claim[];
  event_ids: string[];
  confidence: "high" | "medium" | "low";
  verified: boolean;
  source: "agent" | "template";
  trace_id: string | null;
  prompt_version: string;
}

export interface PersonalizedText {
  insight_id: string;
  persona: Persona;
  lang: Lang;
  headline: string;
  body: string;
  verified: boolean;
  club_id: string | null;
  player_id: string | null;
  dir: "ltr" | "rtl";
  source: "agent" | "template";
}

export interface InsightRow {
  insight: Insight;
  text: PersonalizedText;
  /** The insight's first cited decision event (TASK-23.4); null when it has none. */
  best_play_event_id: string | null;
}

export interface Option {
  kind: "pass" | "through" | "carry" | "shot" | "clear";
  target_player_id: string | null;
  end: [number, number];
  score: number;
  pc_prob: number;
  xt_gain: number;
}

export interface Counterfactual {
  event_id: string;
  chosen: Option;
  best: Option;
  gain: number;
  alternatives: Option[];
}

export interface AgentRun {
  run_id: string;
  agent: string;
  moment_id: string | null;
  status: "ok" | "retry" | "failed" | "fallback";
  attempts: number;
  latency_ms: number;
  trace_id: string | null;
  error: string | null;
  tokens_in: number;
  tokens_out: number;
}

export interface Why {
  claims: Claim[];
  events: MatchEvent[];
  agent_runs: AgentRun[];
  trace_id: string | null;
  counterfactual: Counterfactual | null;
}

export interface Stats {
  metrics: Record<string, number | null>;
  baseline: Record<string, number> | null;
  profile: Record<string, unknown>;
}

export interface PitchControl {
  grid: number[][];
  attacking_team: string;
}

export interface Recap {
  match_id: string;
  title: string;
  paragraphs: string[];
  key_numbers: Claim[];
  verified: boolean;
  source: "agent" | "template";
  /** The recap's language: the fan's, or "en" when no translation is stored. */
  lang: Lang;
}

export interface League {
  clubs: Club[];
  players: Player[];
}

export interface Cue {
  cue_id: string;
  match_id: string;
  period: Period;
  t_in: number;
  t_out: number;
  kind: string;
  priority: number;
  payload: Record<string, unknown>;
}

/** What the live stream sends when an insight's moment ends. */
export interface LiveInsight {
  insight_id: string;
  moment_id: string;
  level: Level;
  headline: string;
  source: "agent" | "template";
  live_line: string | null;
}

export interface RegenerateBody {
  moment_id: string;
  persona: Persona;
  lang: Lang;
  club_id?: string;
  player_id?: string;
}

export interface Regenerated {
  insight: Insight;
  text: PersonalizedText;
  agent_runs: AgentRun[];
  trace_id: string | null;
}
