import type { Session } from '@supabase/supabase-js';
import { createContext } from 'react';

export interface AuthContextValue {
  session: Session | null;
  loading: boolean;
  /** True when the session is the demo bypass (not a real Supabase account);
   * account actions like changing a password don't apply. */
  isDemo: boolean;
  /** Username + password sign-in — repeatable, no email round-trip. The username
   * is mapped to a synthetic email under the hood (see lib/usernameAuth). */
  signInWithUsername: (username: string, password: string) => Promise<void>;
  /** Create a username + password account. With email confirmation off (and no
   * real inbox on the synthetic address), sign-up returns a live session. */
  signUpWithUsername: (username: string, password: string) => Promise<void>;
  /** Start the Google OAuth flow (redirects to Google, then back to /signin).
   * Unlike the username path this yields a real, deliverable email, so these
   * accounts can receive transactional email. On success the browser navigates
   * away, so the returned promise only rejects — it never resolves in-page. */
  signInWithGoogle: () => Promise<void>;
  /** Confirm the signed-in account's current password (re-auth). Resolves true
   * when it matches, false when it doesn't. */
  verifyCurrentPassword: (currentPassword: string) => Promise<boolean>;
  /** Set a new password for the signed-in Supabase account. */
  changePassword: (newPassword: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
