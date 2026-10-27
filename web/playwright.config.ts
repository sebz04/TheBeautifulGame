import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against a separate API on a seeded, model-free database
// (scripts/seed_demo.py) and the built site served by `vite preview`.
const apiPort = process.env.E2E_API_PORT ?? "8100";
const repo = new URL("..", import.meta.url).pathname;
const dataDir = process.env.E2E_DATA_DIR ?? `${repo}data/e2e`;
const dbUrl = process.env.E2E_DB_URL ?? `sqlite:///${dataDir}/e2e.db`;

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: "http://localhost:4173", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `uv run --project ${repo} uvicorn matchmind.api.app:app --port ${apiPort}`,
      cwd: repo,
      url: `http://localhost:${apiPort}/api/health`,
      env: { MATCHMIND_DB_URL: dbUrl, MATCHMIND_DATA_DIR: dataDir, MATCHMIND_APPINSIGHTS_CONNECTION_STRING: "off" },
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run build && npx vite preview --strictPort",
      url: "http://localhost:4173",
      env: { MATCHMIND_API_ORIGIN: `http://localhost:${apiPort}` },
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
