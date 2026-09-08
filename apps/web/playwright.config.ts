import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  use: {
    baseURL: "http://127.0.0.1:3101",
    viewport: { width: 1505, height: 1045 },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "cd ../backend && uv run ../../ops/e2e_server.py",
      url: "http://127.0.0.1:8101/health/ready",
      reuseExistingServer: false,
      timeout: 120000,
    },
    {
      command:
        "API_INTERNAL_URL=http://127.0.0.1:8101 NEXT_DIST_DIR=.next-e2e npx next dev --hostname 127.0.0.1 --port 3101",
      url: "http://127.0.0.1:3101",
      reuseExistingServer: false,
      timeout: 120000,
    },
  ],
});
