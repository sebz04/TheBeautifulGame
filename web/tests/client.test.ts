import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "../src/api/client";

function stubFetch(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fn = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("turns a 429 into an ApiError with retry_after", async () => {
    stubFetch(429, { detail: "too many live runs; try again later", retry_after: 120 });
    const call = api.regenerate("m1", { moment_id: "m1-m001", persona: "casual", lang: "en" });
    await expect(call).rejects.toBeInstanceOf(ApiError);
    await call.catch((e: ApiError) => {
      expect(e.status).toBe(429);
      expect(e.retry_after).toBe(120);
      expect(e.detail).toMatch(/too many/);
    });
  });

  it("builds the insights query", async () => {
    const fetch = stubFetch(200, []);
    await api.insights("m1", { persona: "club_fan", lang: "es", club_id: "chapinero" });
    expect(fetch).toHaveBeenCalledWith(
      "/api/matches/m1/insights?persona=club_fan&lang=es&club_id=chapinero",
      expect.anything(),
    );
  });

  it("posts the regenerate body as JSON", async () => {
    const fetch = stubFetch(200, { insight: {}, text: {}, agent_runs: [], trace_id: null });
    await api.regenerate("m1", { moment_id: "m1-m001", persona: "analyst", lang: "fr" });
    const [, init] = fetch.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ moment_id: "m1-m001", persona: "analyst", lang: "fr" });
  });

  it("uses the API's detail on a 404", async () => {
    stubFetch(404, { detail: "unknown match 'nope'" });
    await expect(api.match("nope")).rejects.toMatchObject({ status: 404, detail: "unknown match 'nope'" });
  });
});
