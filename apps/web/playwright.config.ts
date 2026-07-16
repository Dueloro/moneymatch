import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for the Phase-3 head-to-head e2e (two browser contexts).
 *
 * This suite drives the **real product loop** against a running full stack
 * (`make dev` brings up db + api + worker + web) with the host game API stubbed
 * by a fixture, so settlement resolves deterministically. It is intentionally
 * **not** part of the unit-test CI job (it needs the whole stack + browsers);
 * run it with `make e2e`. See `apps/web/e2e/README.md` for prerequisites.
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
