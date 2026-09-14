import { defineConfig } from "@playwright/test";

// Inline `VAR=value command` is a POSIX shell form that cmd.exe cannot run, so the
// two variables next.config.ts reads are set here instead. Both point the dev server
// at the synthetic e2e backend and keep its build out of .next.
process.env.API_INTERNAL_URL = "http://127.0.0.1:8101";
process.env.NEXT_DIST_DIR = ".next-e2e";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  // The webServer below is a dev server, so a route is compiled the first time a
  // test hits it. On this machine that can outlast the 5s default and fail a
  // navigation the app performed correctly; every assertion here settles in well
  // under this when the route is warm.
  expect: { timeout: 15000 },
  use: {
    baseURL: "http://127.0.0.1:3101",
    viewport: { width: 1505, height: 1045 },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      // `uv run ../../ops/e2e_server.py` picks a different environment for a script
      // outside the project and cannot import the backend's own dependencies. Naming
      // the project and the interpreter keeps the browser tests on this backend.
      command: "cd ../backend && uv run --project . python ../../ops/e2e_server.py",
      url: "http://127.0.0.1:8101/health/ready",
      reuseExistingServer: false,
      timeout: 120000,
      // The worker paces platform fetches at one per 300s, which is right in
      // production and useless for a suite that posts several sources in a minute.
      // Nothing here reaches the platform and STORAGE_BACKEND is local, so the gate
      // is disabled for this run through the server's own settings.
      env: { PLATFORM_FETCH_INTERVAL_SECONDS: "0" },
    },
    {
      command: "npx next dev --hostname 127.0.0.1 --port 3101",
      url: "http://127.0.0.1:3101",
      reuseExistingServer: false,
      timeout: 120000,
    },
  ],
});
