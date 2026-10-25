import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  use: { baseURL: "http://127.0.0.1:13000", trace: "off", screenshot: "off" },
  webServer: [
    {
      command: `"${process.env.GNK_TEST_PYTHON || "python"}" ../backend/tests/browser_server.py`,
      url: "http://127.0.0.1:18080/api/ready",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npm run start -- --hostname 127.0.0.1 --port 13000",
      url: "http://127.0.0.1:13000",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
