import { defineConfig, devices } from "@playwright/test";

/**
 * E2E config.
 *
 * Assumes the backend is already up on :8000 — these tests drive the real stack rather than
 * mocking the API, because the thing worth checking is that a clause citation the engine
 * produced actually reaches the screen. Mocking the API would only test the components
 * against a fixture I wrote, which proves much less.
 *
 * The frontend is started here (and reused if you already have one running).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // the suite shares one backend database
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",

  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },

  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],

  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "npm run start",
        url: "http://localhost:3000",
        reuseExistingServer: true,
        timeout: 120_000,
      },
});
