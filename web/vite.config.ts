/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev server proxies the API (uv run uvicorn matchmind.api.app:app) so the app uses
// same-origin paths, as it will in production.
const api = process.env.MATCHMIND_API_ORIGIN ?? "http://localhost:8000";
const proxy = { "/api": api, "/mcp": api };

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
