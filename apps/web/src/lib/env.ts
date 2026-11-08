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
  posthogKey: optional('VITE_POSTHOG_KEY'),
  posthogHost: optional('VITE_POSTHOG_HOST') ?? 'https://us.i.posthog.com',
  sentryDsn: optional('VITE_SENTRY_DSN'),
  e2eAuth: optional('VITE_E2E_AUTH') === 'true',
};
