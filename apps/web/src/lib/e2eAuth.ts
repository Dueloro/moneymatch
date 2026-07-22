// Local sign-in bypass for e2e (backlog · "Browser e2e test-auth seam").
//
// When VITE_E2E_AUTH === 'true', the app authenticates from an access token that
// the Playwright harness writes to localStorage (minted by the API's
// `/dev/e2e/token` route for a seeded user), instead of a live Supabase session.
// This code path is inert in a normal build: `env.e2eAuth` is false, so every
// helper short-circuits and the real Supabase flow runs unchanged.

import { env } from './env';

export const E2E_TOKEN_KEY = 'mm.e2e.access_token';

/** The injected e2e access token, or null when the bypass is off / unset. */
export function getE2eToken(): string | null {
  if (!env.e2eAuth) return null;
  try {
    return window.localStorage.getItem(E2E_TOKEN_KEY);
  } catch {
    return null;
  }
}

export interface E2eClaims {
  sub: string;
  email?: string;
}

/** Decode a JWT's payload (no signature check — the API verifies that). */
export function decodeJwtClaims(token: string): E2eClaims | null {
  try {
    const payload = token.split('.')[1];
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    const claims = JSON.parse(json) as { sub?: string; email?: string };
    if (!claims.sub) return null;
    return { sub: claims.sub, email: claims.email };
  } catch {
    return null;
  }
}
