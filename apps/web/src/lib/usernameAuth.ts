const AUTH_EMAIL_DOMAIN = 'users.moneymatch.app';

export function emailToUsername(email: string | null | undefined): string | null {
  if (!email) return null;
  const suffix = `@${AUTH_EMAIL_DOMAIN}`;
  const lower = email.toLowerCase();
  return lower.endsWith(suffix) ? lower.slice(0, -suffix.length) : null;
}
