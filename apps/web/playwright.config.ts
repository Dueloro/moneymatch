import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright e2e against a running full stack (`make dev`) with real Lichess handles;
 * not in the unit-test CI job. Run with `make e2e`; see `apps/web/e2e/README.md`.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
