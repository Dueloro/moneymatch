import { createClient } from '@supabase/supabase-js';

import { getE2eToken } from './e2eAuth';
import { env } from './env';

export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});

export async function getAccessToken(): Promise<string | null> {
  const e2e = getE2eToken();
  if (e2e) return e2e;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
