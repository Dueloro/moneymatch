import type { Session } from '@supabase/supabase-js';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { decodeJwtClaims, getE2eToken } from '../lib/e2eAuth';
import { env } from '../lib/env';
import { supabase } from '../lib/supabase';
import { identify, resetIdentity } from '../lib/telemetry';
import { AuthContext, type AuthContextValue } from './authContext';

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
  const [passwordRecovery, setPasswordRecovery] = useState(false);

  useEffect(() => {
    if (env.e2eAuth) {
      const token = getE2eToken();
      const injected = token ? sessionFromToken(token) : null;
      setSession(injected);
      if (injected) identify(injected.user.id);
      setLoading(false);
      return;
    }
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
        void supabase.auth.signOut({ scope: 'local' });
        finish(null);
      });
    const { data: sub } = supabase.auth.onAuthStateChange((event, next) => {
      setSession(next);
      if (event === 'PASSWORD_RECOVERY') setPasswordRecovery(true);
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
      isPasswordRecovery: passwordRecovery,
      signUpWithEmail: async (email: string, password: string) => {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: { emailRedirectTo: `${window.location.origin}/signin` },
        });
        if (error) throw error;
        return { needsVerification: data.session === null };
      },
      signInWithEmail: async (email: string, password: string) => {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      },
      sendLoginCode: async (email: string) => {
        const { error } = await supabase.auth.signInWithOtp({
          email,
          options: { shouldCreateUser: false },
        });
        if (error) throw error;
      },
      verifyLoginCode: async (email: string, token: string) => {
        const { error } = await supabase.auth.verifyOtp({
          email,
          token,
          type: 'email',
        });
        if (error) throw error;
      },
      sendPasswordReset: async (email: string) => {
        const { error } = await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: `${window.location.origin}/signin`,
        });
        if (error) throw error;
      },
      setNewPassword: async (password: string) => {
        const { error } = await supabase.auth.updateUser({ password });
        if (error) throw error;
        setPasswordRecovery(false);
      },
      signInWithGoogle: async () => {
        const { error } = await supabase.auth.signInWithOAuth({
          provider: 'google',
          options: { redirectTo: `${window.location.origin}/signin` },
        });
        if (error) throw error;
      },
      verifyCurrentPassword: async (currentPassword: string) => {
        const email = session?.user.email;
        if (!email) return false;
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
        await supabase.auth.signOut({ scope: 'local' }).catch(() => undefined);
        resetIdentity();
        setSession(null);
      },
    }),
    [session, loading, passwordRecovery],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
