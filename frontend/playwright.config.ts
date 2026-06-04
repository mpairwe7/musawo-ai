import { defineConfig, devices } from "@playwright/test";

// Target the deployed Crane Cloud app by default; override with E2E_BASE_URL.
const BASE_URL =
  process.env.E2E_BASE_URL || "https://musawo-ai-ce243528.renu-01.cranecloud.io";

export default defineConfig({
  testDir: "./e2e",
  // Live backend + Groq quota — keep it gentle and deterministic.
  fullyParallel: false,
  workers: 1,
  // These hit a live PaaS deployment — tolerate transient gateway blips (e.g. a
  // 502/504 during a pod rollover) by retrying before failing.
  retries: process.env.CI ? 2 : 1,
  timeout: 90_000, // LLM calls on the offline-mode pod can be slow
  expect: { timeout: 20_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: BASE_URL,
    extraHTTPHeaders: { "x-request-id": "e2e-playwright" },
    trace: "retain-on-failure",
    actionTimeout: 20_000,
    navigationTimeout: 45_000,
  },
  projects: [
    // API regression — pure HTTP, no browser needed (run with --project=api)
    { name: "api", testMatch: /api\.spec\.ts/ },
    // Browser E2E against the deployed frontend
    {
      name: "chromium",
      testMatch: /app\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
