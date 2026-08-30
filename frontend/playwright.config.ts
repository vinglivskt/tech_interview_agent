import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  // LLM-ручки могут работать до 60 секунд (особенно sobes/start с классификацией).
  timeout: 90_000,
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:3000",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: !process.env.CI,
  },
});
