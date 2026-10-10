import { defineConfig, devices } from "@playwright/test";

// UI tests run the real API (LLM replay from tests/cassettes) against a dedicated database, reset per test with
// POST /dev/seed. Point E2E_DATABASE_URL at your Postgres (the database name is replaced with rs_e2e).
const API_PORT = 8799;
const WEB_PORT = 5199;
const base = process.env.E2E_DATABASE_URL ?? "postgresql+asyncpg://rs:rs@localhost:5432/rs";
const dbUrl = base.replace(/\/[^/]+$/, "/rs_e2e");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: `http://localhost:${WEB_PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: [
    {
      command: `uv run python tools/e2e_db.py && uv run uvicorn apps.api.main:app --factory --port ${API_PORT}`,
      cwd: "../..",
      url: `http://localhost:${API_PORT}/healthz`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        RS_DATABASE_URL: dbUrl, RS_ENV: "dev", RS_LLM_MODE: "replay", RS_EMAIL_SENDER: "off",
        RS_WEB_BASE_URL: `http://localhost:${WEB_PORT}`,
        RS_PUBLIC_BASE_URL: `http://localhost:${API_PORT}`,
      },
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: !process.env.CI,
      env: { BACKEND_URL: `http://localhost:${API_PORT}` },
    },
  ],
});
