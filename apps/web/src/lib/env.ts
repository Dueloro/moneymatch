// Typed, validated access to the browser env. Fail loud in dev if a required
// VITE_ var is missing rather than erroring deep inside Supabase/api calls.

function required(name: keyof ImportMetaEnv): string {
  const value = import.meta.env[name];
  if (!value) {
    throw new Error(`Missing required env var ${name}. See .env.example.`);
  }
  return value;
}

function optional(name: keyof ImportMetaEnv): string | undefined {
  const value = import.meta.env[name];
  return value ? String(value) : undefined;
}

export const env = {
  apiBaseUrl: required('VITE_API_BASE_URL'),
  supabaseUrl: required('VITE_SUPABASE_URL'),
  supabaseAnonKey: required('VITE_SUPABASE_ANON_KEY'),
  // Optional: with no key, client telemetry stays console-only (Phase 6).
  posthogKey: optional('VITE_POSTHOG_KEY'),
  posthogHost: optional('VITE_POSTHOG_HOST') ?? 'https://us.i.posthog.com',
  // Optional: with no DSN, Sentry error tracking is disabled.
  sentryDsn: optional('VITE_SENTRY_DSN'),
  // Dev/e2e only: local sign-in bypass (backlog · "Browser e2e test-auth seam").
  // Never 'true' in a production build.
  e2eAuth: optional('VITE_E2E_AUTH') === 'true',
};
