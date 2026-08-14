import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from './AuthProvider';
import { useAuth } from './useAuth';

// vi.mock calls are hoisted to the top of the file, so the `auth` object must
// also be hoisted via vi.hoisted so it exists at factory-evaluation time.
const auth = vi.hoisted(() => ({
  getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
  onAuthStateChange: vi.fn().mockReturnValue({
    data: { subscription: { unsubscribe: vi.fn() } },
  }),
  signUp: vi.fn(),
  signInWithPassword: vi.fn(),
  signInWithOtp: vi.fn(),
  verifyOtp: vi.fn(),
  resetPasswordForEmail: vi.fn(),
  updateUser: vi.fn(),
  signInWithOAuth: vi.fn(),
  signOut: vi.fn().mockResolvedValue({}),
}));

vi.mock('./lib/supabase', () => ({}));
vi.mock('../lib/supabase', () => ({ supabase: { auth } }));
vi.mock('../lib/telemetry', () => ({
  identify: vi.fn(),
  resetIdentity: vi.fn(),
}));

const wrapper = ({ children }: { children: ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
);

describe('AuthProvider email methods', () => {
  beforeEach(() => vi.clearAllMocks());

  it('signUpWithEmail reports needsVerification when no session returns', async () => {
    auth.signUp.mockResolvedValue({ data: { session: null }, error: null });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    let out!: { needsVerification: boolean };
    await act(async () => {
      out = await result.current.signUpWithEmail('a@b.com', 'secret6');
    });
    expect(auth.signUp).toHaveBeenCalledWith({
      email: 'a@b.com',
      password: 'secret6',
      options: { emailRedirectTo: `${window.location.origin}/signin` },
    });
    expect(out.needsVerification).toBe(true);
  });

  it('sendLoginCode requests an OTP without creating a user', async () => {
    auth.signInWithOtp.mockResolvedValue({ error: null });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => result.current.sendLoginCode('a@b.com'));
    expect(auth.signInWithOtp).toHaveBeenCalledWith({
      email: 'a@b.com',
      options: { shouldCreateUser: false },
    });
  });

  it('verifyLoginCode verifies the emailed token', async () => {
    auth.verifyOtp.mockResolvedValue({ error: null });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => result.current.verifyLoginCode('a@b.com', '123456'));
    expect(auth.verifyOtp).toHaveBeenCalledWith({
      email: 'a@b.com',
      token: '123456',
      type: 'email',
    });
  });
});
