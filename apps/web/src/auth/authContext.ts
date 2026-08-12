import type { Session } from '@supabase/supabase-js';
import { createContext } from 'react';

export interface AuthContextValue {
  session: Session | null;
  loading: boolean;
  /** True when the session is the demo bypass (not a real Supabase account). */
  isDemo: boolean;
  /** True after arriving via a password-reset link (Supabase PASSWORD_RECOVERY);
   * the sign-in screen shows the set-new-password step while this holds. */
  isPasswordRecovery: boolean;
  /** Create an account with a real email + password. Resolves
   * `{ needsVerification: true }` when Supabase withholds the session pending
   * email confirmation (the expected first-time path), else `false`. */
  signUpWithEmail: (
    email: string,
    password: string,
  ) => Promise<{ needsVerification: boolean }>;
  /** Email + password sign-in for a verified account. */
  signInWithEmail: (email: string, password: string) => Promise<void>;
  /** Send a one-time login code to an existing account's email (no new account). */
  sendLoginCode: (email: string) => Promise<void>;
  /** Verify the emailed login code, establishing a session. */
  verifyLoginCode: (email: string, token: string) => Promise<void>;
  /** Email a password-reset link. */
  sendPasswordReset: (email: string) => Promise<void>;
  /** Set a new password for the recovery-authenticated session. */
  setNewPassword: (password: string) => Promise<void>;
  /** Start the Google OAuth flow (redirects away, only rejects in-page). */
  signInWithGoogle: () => Promise<void>;
  /** Confirm the signed-in account's current password (re-auth). */
  verifyCurrentPassword: (currentPassword: string) => Promise<boolean>;
  /** Set a new password for the signed-in Supabase account. */
  changePassword: (newPassword: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
