import { defineConfig } from "@playwright/test";

// End-to-end tests start their own API (fake providers: free, deterministic, no keys) and
// their own Next dev server on separate ports, so they never touch a running dev stack's
// settings. They do use the local Postgres and Redis from compose.yaml.
//
//   Windows:  $env:KV_PYTHON=".venv\Scripts\python"; $env:PW_CHANNEL="msedge"; npm run test:e2e
//   CI/Linux: npx playwright install chromium && npm run test:e2e
const API_PORT = 8100;
const WEB_PORT = 3100;
const python = process.env.KV_PYTHON ?? "python";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    channel: process.env.PW_CHANNEL || undefined, // e.g. "msedge" to use an installed browser
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `${python} -m uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${API_PORT}/ready`,
      timeout: 60_000,
      reuseExistingServer: false,
      env: {
        EVALUATOR_PROVIDER: "fake",
        RESPONDER_PROVIDER: "fake",
        LLM_API_KEY: "",
        LIVEKIT_URL: "",
        LIVEKIT_API_KEY: "",
        LIVEKIT_API_SECRET: "",
        VOICE_WORKER_SECRET: "",
        RATE_LIMIT_ENABLED: "false",
        FRONTEND_ORIGIN: `http://localhost:${WEB_PORT}`,
      },
    },
    {
      command: `npx next dev -p ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        NEXT_PUBLIC_API_BASE_URL: `http://127.0.0.1:${API_PORT}`,
        NEXT_DIST_DIR: ".next-e2e",
      },
    },
  ],
});
