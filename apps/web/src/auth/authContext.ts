import type { Session } from '@supabase/supabase-js';
import { createContext } from 'react';

export interface AuthContextValue {
  session: Session | null;
  loading: boolean;
  isPasswordRecovery: boolean;
  signUpWithEmail: (
    email: string,
    password: string,
  ) => Promise<{ needsVerification: boolean }>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  sendLoginCode: (email: string) => Promise<void>;
  verifyLoginCode: (email: string, token: string) => Promise<void>;
  sendPasswordReset: (email: string) => Promise<void>;
  setNewPassword: (password: string) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  verifyCurrentPassword: (currentPassword: string) => Promise<boolean>;
  changePassword: (newPassword: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
