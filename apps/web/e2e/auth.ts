import { request, type Browser, type Page } from '@playwright/test';

/**
 * Shared e2e sign-in via the local test-auth seam (backlog · "Browser e2e
 * test-auth seam"). Instead of injecting a live Supabase session, each context
 * authenticates with a short-lived token minted by the API's `/dev/e2e/token`
 * route for a seeded `auth_id`, written to the localStorage key the web app
 * reads when built with `VITE_E2E_AUTH=true` (see web `src/lib/e2eAuth.ts`).
 *
 * Enable the suite by running the stack with the seam on and setting `E2E_AUTH`:
 *   API:  E2E_AUTH_ENABLED=true SUPABASE_JWT_SECRET=<secret> …  (make dev)
 *   web:  VITE_E2E_AUTH=true                                     (vite build/dev)
 *   run:  E2E_AUTH=1 make e2e
 */

const E2E_TOKEN_KEY = 'mm.e2e.access_token';
const API_BASE = process.env.E2E_API_BASE_URL ?? 'http://localhost:8000';

/** True when the run is configured for the bypass; specs skip otherwise so they
 * never silently pass. */
export function e2eAuthConfigured(): boolean {
  return process.env.E2E_AUTH === '1' || process.env.E2E_AUTH === 'true';
}

/** Mint an access token for a seeded user through the API's dev/e2e route. */
export async function mintToken(authId: string, email?: string): Promise<string> {
  const ctx = await request.newContext();
  try {
    const resp = await ctx.post(`${API_BASE}/api/v1/dev/e2e/token`, {
      data: { auth_id: authId, email },
    });
    if (!resp.ok()) {
      throw new Error(
        `e2e token mint failed (${resp.status()}) for ${authId} — is the API up ` +
          `with E2E_AUTH_ENABLED=true and SUPABASE_JWT_SECRET set?`,
      );
    }
    const body = (await resp.json()) as { access_token: string };
    return body.access_token;
  } finally {
    await ctx.dispose();
  }
}

/** Open an authenticated page for a seeded user in a fresh browser context. */
export async function signInAs(
  browser: Browser,
  authId: string,
  opts: { path?: string; email?: string } = {},
): Promise<Page> {
  const token = await mintToken(authId, opts.email);
  const context = await browser.newContext();
  await context.addInitScript(
    ({ key, value }) => window.localStorage.setItem(key, value),
    { key: E2E_TOKEN_KEY, value: token },
  );
  const page = await context.newPage();
  if (opts.path) await page.goto(opts.path);
  return page;
}
