import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  use: { baseURL: "http://127.0.0.1:3001", browserName: "chromium" },
  webServer: {
    command: "npm run start",
    url: "http://127.0.0.1:3001/health",
    env: { PORT: "3001" },
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
