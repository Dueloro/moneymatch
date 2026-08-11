import type { Session } from '@supabase/supabase-js';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { clearDemoToken, getDemoToken } from '../lib/demoAuth';
import { decodeJwtClaims, getE2eToken } from '../lib/e2eAuth';
import { env } from '../lib/env';
import { supabase } from '../lib/supabase';
import { identify, resetIdentity } from '../lib/telemetry';
import { usernameToEmail } from '../lib/usernameAuth';
import { AuthContext, type AuthContextValue } from './authContext';

/** Build a minimal Supabase-shaped session from an injected access token (demo
 * or e2e) so the app routes past RequireAuth without a live Supabase session. */
function sessionFromToken(token: string): Session | null {
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
    // Demo bypass: adopt the demo token as the session, skip Supabase entirely.
    // The token is only in localStorage after a successful /demo/login, and the
    // backend only honours it while demo mode is on.
    const demoToken = getDemoToken();
    if (demoToken) {
      const injected = sessionFromToken(demoToken);
      if (injected) {
        setSession(injected);
        identify(injected.user.id);
        setLoading(false);
        return;
      }
    }
    // e2e bypass: adopt the injected token as the session, skip Supabase entirely.
    if (env.e2eAuth) {
      const token = getE2eToken();
      const injected = token ? sessionFromToken(token) : null;
      setSession(injected);
      if (injected) identify(injected.user.id);
      setLoading(false);
      return;
    }
    // Restore the Supabase session, but never let bootstrap hang the app. A
    // stale/corrupt token in localStorage can leave getSession() pending
    // indefinitely; without a bound, `loading` never clears and every route is
    // stuck on the "Loading…" gate. Cap it, and always resolve to a definite
    // signed-in/out state so a broken session falls through to sign-in.
    let settled = false;
    const finish = (next: Session | null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      setSession(next);
      if (next) identify(next.user.id);
      setLoading(false);
    };
    const timer = setTimeout(() => finish(null), 8000);
    supabase.auth
      .getSession()
      .then(({ data }) => finish(data.session))
      .catch(() => {
        // The stored session is unusable — clear it locally (no network) so the
        // next load doesn't hang on the same bad token, then show sign-in.
        void supabase.auth.signOut({ scope: 'local' });
        finish(null);
      });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      // Tie analytics to the user id after auth; drop it on sign-out so the
      // activation funnel attributes to the right person (09-phase-6 · d.3).
      if (next) identify(next.user.id);
      else resetIdentity();
    });
    return () => {
      clearTimeout(timer);
      sub.subscription.unsubscribe();
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      loading,
      isDemo: getDemoToken() != null,
      signInWithUsername: async (username: string, password: string) => {
        const { error } = await supabase.auth.signInWithPassword({
          email: usernameToEmail(username),
          password,
        });
        if (error) throw error;
      },
      signUpWithUsername: async (username: string, password: string) => {
        const { data, error } = await supabase.auth.signUp({
          email: usernameToEmail(username),
          password,
        });
        if (error) throw error;
        // Autoconfirm must stay ON for this project: the synthetic address has no
        // inbox, so if email confirmation is ever re-enabled, signUp returns no
        // session and the app would silently stall on the sign-in screen. Fail
        // loud with a message the UI can explain instead.
        if (!data.session) throw new Error('email_confirmation_required');
      },
      signInWithGoogle: async () => {
        // Full-page redirect to Google and back to /signin, where the flow
        // resumes: detectSessionInUrl adopts the returned session and
        // onAuthStateChange advances a new user into onboarding. Because a Google
        // account carries a real email, emailToUsername() returns null and the
        // onboarding step prompts for a handle (username accounts skip that).
        const { error } = await supabase.auth.signInWithOAuth({
          provider: 'google',
          options: { redirectTo: `${window.location.origin}/signin` },
        });
        if (error) throw error;
      },
      verifyCurrentPassword: async (currentPassword: string) => {
        const email = session?.user.email;
        if (!email) return false;
        // Re-authenticate to confirm the password; on success Supabase returns a
        // fresh session for the same user (no disruption).
        const { error } = await supabase.auth.signInWithPassword({
          email,
          password: currentPassword,
        });
        return !error;
      },
      changePassword: async (newPassword: string) => {
        const { error } = await supabase.auth.updateUser({ password: newPassword });
        if (error) throw error;
      },
      signOut: async () => {
        // A demo session isn't a Supabase session, so clear the token and reset
        // locally; a real session signs out through Supabase as usual.
        const wasDemo = getDemoToken() != null;
        clearDemoToken();
        await supabase.auth.signOut({ scope: 'local' }).catch(() => undefined);
        resetIdentity();
        setSession(null);
        if (wasDemo) {
          window.location.assign('/signin');
        }
      },
    }),
    [session, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
