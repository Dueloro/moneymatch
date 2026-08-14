// Synthetic-email addresses (@users.moneymatch.app) backed the retired
// username-as-login scheme. Real email is now the credential; this helper only
// recognises a leftover synthetic address so onboarding never treats it as a
// real handle source.
const AUTH_EMAIL_DOMAIN = 'users.moneymatch.app';

/** Recover the username from a legacy synthetic email, or null for a real one. */
export function emailToUsername(email: string | null | undefined): string | null {
  if (!email) return null;
  const suffix = `@${AUTH_EMAIL_DOMAIN}`;
  const lower = email.toLowerCase();
  return lower.endsWith(suffix) ? lower.slice(0, -suffix.length) : null;
}
