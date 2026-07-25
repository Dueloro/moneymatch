import type { Session } from '@supabase/supabase-js';
import { createContext } from 'react';

export interface AuthContextValue {
  session: Session | null;
  loading: boolean;
  /** True when the session is the demo bypass (not a real Supabase account);
   * account actions like changing a password don't apply. */
  isDemo: boolean;
  signInWithGoogle: () => Promise<void>;
  /** Magic-link (OTP) sign-in. Kept for compatibility; the UI uses passwords. */
  signInWithEmail: (email: string) => Promise<void>;
  /** Email + password sign-in — repeatable, no email round-trip. */
  signInWithPassword: (email: string, password: string) => Promise<void>;
  /** Create an email + password account. `needsConfirmation` is true when the
   * Supabase project still requires email confirmation before first sign-in. */
  signUpWithPassword: (
    email: string,
    password: string,
  ) => Promise<{ needsConfirmation: boolean }>;
  /** Confirm the signed-in account's current password (re-auth). Resolves true
   * when it matches, false when it doesn't. */
  verifyCurrentPassword: (currentPassword: string) => Promise<boolean>;
  /** Email the signed-in account a password-reset link (the "forgot password"
   * fallback when they can't confirm their current password). */
  sendPasswordReset: () => Promise<void>;
  /** Set a new password for the signed-in Supabase account. */
  changePassword: (newPassword: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
