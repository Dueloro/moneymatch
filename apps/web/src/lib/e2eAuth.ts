import { env } from './env';

export const E2E_TOKEN_KEY = 'mm.e2e.access_token';

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
