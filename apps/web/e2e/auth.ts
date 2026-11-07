import { request, type Browser, type Page } from '@playwright/test';

const E2E_TOKEN_KEY = 'mm.e2e.access_token';
export const API_BASE = process.env.E2E_API_BASE_URL ?? 'http://localhost:8000';

export function e2eAuthConfigured(): boolean {
  return process.env.E2E_AUTH === '1' || process.env.E2E_AUTH === 'true';
}

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
