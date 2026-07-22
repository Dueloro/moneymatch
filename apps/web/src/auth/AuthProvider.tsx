import type { Session } from '@supabase/supabase-js';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { decodeJwtClaims, getE2eToken } from '../lib/e2eAuth';
import { env } from '../lib/env';
import { supabase } from '../lib/supabase';
import { identify, resetIdentity } from '../lib/telemetry';
import { AuthContext, type AuthContextValue } from './authContext';

/** Build a minimal Supabase-shaped session from an e2e access token so the app
 * routes past RequireAuth without a live Supabase project. */
function e2eSession(token: string): Session | null {
  const claims = decodeJwtClaims(token);
  if (!claims) return null;
  return {
    access_token: token,
    token_type: 'bearer',
    user: { id: claims.sub, email: claims.email },
  } as unknown as Session;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // e2e bypass: adopt the injected token as the session, skip Supabase entirely.
    if (env.e2eAuth) {
      const token = getE2eToken();
      const injected = token ? e2eSession(token) : null;
      setSession(injected);
      if (injected) identify(injected.user.id);
      setLoading(false);
      return;
    }
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      if (data.session) identify(data.session.user.id);
      setLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      // Tie analytics to the user id after auth; drop it on sign-out so the
      // activation funnel attributes to the right person (09-phase-6 · d.3).
      if (next) identify(next.user.id);
      else resetIdentity();
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      loading,
      signInWithGoogle: async () => {
        await supabase.auth.signInWithOAuth({
          provider: 'google',
          options: { redirectTo: window.location.origin },
        });
      },
      signInWithEmail: async (email: string) => {
        const { error } = await supabase.auth.signInWithOtp({
          email,
          options: { emailRedirectTo: window.location.origin },
        });
        if (error) throw error;
      },
      signOut: async () => {
        await supabase.auth.signOut();
      },
    }),
    [session, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
