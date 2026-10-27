// The typed API client. Same-origin paths: Vite proxies /api in development, and the
// API serves the built site in production.
import type {
  InsightRow,
  Lang,
  League,
  MatchDetail,
  MatchRow,
  Period,
  Persona,
  PitchControl,
  Recap,
  RegenerateBody,
  Regenerated,
  Stats,
  Timeline,
  Why,
  Frame,
} from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly retry_after?: number,
  ) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
  }
}

type Query = Record<string, string | number | undefined | null>;

function withQuery(path: string, query?: Query): string {
  const parts = Object.entries(query ?? {})
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `${path}?${parts.join("&")}` : path;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(path, { headers: { Accept: "application/json", ...init.headers }, ...init });
  const body: unknown = await resp.json().catch(() => null);
  if (!resp.ok) {
    const b = (body ?? {}) as { detail?: unknown; retry_after?: number };
    const detail = typeof b.detail === "string" ? b.detail : resp.statusText || "request failed";
    throw new ApiError(resp.status, detail, b.retry_after);
  }
  return body as T;
}

const get = <T>(path: string, query?: Query) => request<T>(withQuery(path, query), { method: "GET" });

export interface InsightQuery {
  persona: Persona;
  lang: Lang;
  club_id?: string;
  player_id?: string;
}

export interface StatsQuery {
  scope: "team" | "player";
  scope_id: string;
  period: Period;
  t: number;
}

export const api = {
  matches: () => get<MatchRow[]>("/api/matches"),
  match: (id: string) => get<MatchDetail>(`/api/matches/${id}`),
  tracking: (id: string, period: Period, from: number, to: number) =>
    get<{ frames: Frame[] }>(`/api/matches/${id}/tracking`, { period, from, to }),
  timeline: (id: string) => get<Timeline>(`/api/matches/${id}/timeline`),
  insights: (id: string, q: InsightQuery) =>
    get<InsightRow[]>(`/api/matches/${id}/insights`, { ...q }).then((rows) =>
      rows.map((r) => ({ ...r, best_play_event_id: r.best_play_event_id ?? null })),
    ),
  why: (insightId: string) => get<Why>(`/api/insights/${insightId}/why`),
  stats: (id: string, q: StatsQuery) => get<Stats>(`/api/matches/${id}/stats`, { ...q }),
  pitchControl: (id: string, period: Period, t: number) =>
    get<PitchControl>(`/api/matches/${id}/pitch-control`, { period, t }),
  recap: (id: string, lang: Lang) => get<Recap>(`/api/matches/${id}/recap`, { lang }),
  league: () => get<League>("/api/league"),
  regenerate: (id: string, body: RegenerateBody) =>
    request<Regenerated>(`/api/matches/${id}/regenerate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};
