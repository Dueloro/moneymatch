import type { Session } from '@supabase/supabase-js';
import { createContext } from 'react';

export interface AuthContextValue {
  session: Session | null;
  loading: boolean;
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
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
