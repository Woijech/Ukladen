import { defineConfig } from "@playwright/test";
import { testOrigin, testPort } from "./tests/test-origin";

export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: testOrigin,
    browserName: "chromium",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : undefined,
  },
  webServer: {
    command: "npm run start",
    url: `${testOrigin}/health`,
    env: { PORT: testPort },
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
