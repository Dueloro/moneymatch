// Complete demo-login bypass. The button mints a demo token from the API
// (`POST /api/v1/demo/login`, enabled by the server's DEMO_LOGIN_ENABLED flag),
// stores it, and the app adopts it as the session — no Supabase, no email. The
// backend accepts this token only while demo mode is on, so a stray token in
// localStorage can never grant real access.

import { decodeJwtClaims } from './e2eAuth';
import { env } from './env';

export const DEMO_TOKEN_KEY = 'mm.demo.access_token';

/** The stored demo token, or null when absent / malformed. */
export function getDemoToken(): string | null {
  try {
    const token = window.localStorage.getItem(DEMO_TOKEN_KEY);
    if (!token) return null;
    // Ignore a garbage token so we never adopt a broken session.
    return decodeJwtClaims(token) ? token : null;
  } catch {
    return null;
  }
}

export function clearDemoToken(): void {
  try {
    window.localStorage.removeItem(DEMO_TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

/** Mint a demo token, store it, and enter the app (full reload so the auth
 * provider adopts it as the session). */
export async function enterDemo(): Promise<void> {
  const res = await fetch(`${env.apiBaseUrl}/api/v1/demo/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  });
  if (!res.ok) {
    throw new Error('Demo login is not enabled on this server.');
  }
  const data = (await res.json()) as { access_token: string };
  window.localStorage.setItem(DEMO_TOKEN_KEY, data.access_token);
  window.location.assign('/play');
}
