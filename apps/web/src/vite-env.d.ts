/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_SUPABASE_URL: string;
  readonly VITE_SUPABASE_ANON_KEY: string;
  readonly VITE_POSTHOG_KEY?: string;
  readonly VITE_POSTHOG_HOST?: string;
  // Dev/e2e only: 'true' enables the local sign-in bypass (see lib/e2eAuth.ts).
  readonly VITE_E2E_AUTH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
