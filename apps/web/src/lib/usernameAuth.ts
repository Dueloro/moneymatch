// Username-as-credential seam. Supabase Auth is email-based, so each username
// maps to a stable, non-deliverable synthetic email under a reserved subdomain.
// The mapping is deterministic, so sign-in needs no lookup — just the transform.
// Supabase's email-uniqueness then doubles as our sign-up username guard.
export const AUTH_EMAIL_DOMAIN = 'users.moneymatch.app';

/** `alice` → `alice@users.moneymatch.app`. Lower-cased to match the citext
 * username column and the `^[a-z0-9_]{3,20}$` rule enforced at input. */
export function usernameToEmail(username: string): string {
  return `${username.trim().toLowerCase()}@${AUTH_EMAIL_DOMAIN}`;
}

/** Recover the username from a synthetic email (e.g. `session.user.email`), or
 * null for a real/foreign address. Lets onboarding show the handle chosen at
 * sign-up even on a later session, with no extra state to carry. */
export function emailToUsername(email: string | null | undefined): string | null {
  if (!email) return null;
  const suffix = `@${AUTH_EMAIL_DOMAIN}`;
  const lower = email.toLowerCase();
  return lower.endsWith(suffix) ? lower.slice(0, -suffix.length) : null;
}
