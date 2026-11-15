import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';

import { HttpError } from '../lib/apiError';
import { renderWithProviders } from '../test/testUtils';
import { RequireAuth } from './RequireAuth';

vi.mock('./useAuth', () => ({ useAuth: vi.fn() }));
vi.mock('../hooks/useMe', () => ({ useMe: vi.fn() }));

import { useAuth } from './useAuth';
import { useMe } from '../hooks/useMe';

const mockUseAuth = vi.mocked(useAuth);
const mockUseMe = vi.mocked(useMe);

function tree() {
  return (
    <Routes>
      <Route path="/signin" element={<div>SIGN IN SCREEN</div>} />
      <Route element={<RequireAuth />}>
        <Route path="/play" element={<div>PLAY SCREEN</div>} />
      </Route>
    </Routes>
  );
}

describe('RequireAuth', () => {
  beforeEach(() => {
    mockUseMe.mockReturnValue({
      data: undefined,
      isLoading: false,
    } as ReturnType<typeof useMe>);
  });

  it('redirects an unauthenticated user to /signin', () => {
    mockUseAuth.mockReturnValue({
      session: null,
      loading: false,
      isPasswordRecovery: false,
      signUpWithEmail: vi.fn(),
      resendVerification: vi.fn(),
      signInWithEmail: vi.fn(),
      sendLoginCode: vi.fn(),
      verifyLoginCode: vi.fn(),
      sendPasswordReset: vi.fn(),
      setNewPassword: vi.fn(),
      signInWithGoogle: vi.fn(),
      verifyCurrentPassword: vi.fn(),
      changePassword: vi.fn(),
      signOut: vi.fn(),
    });
    renderWithProviders(tree(), { route: '/play' });
    expect(screen.getByText('SIGN IN SCREEN')).toBeInTheDocument();
    expect(screen.queryByText('PLAY SCREEN')).not.toBeInTheDocument();
  });

  it('renders the protected route for an onboarded user', () => {
    mockUseAuth.mockReturnValue({
      session: { user: { id: 'u1' } } as never,
      loading: false,
      isPasswordRecovery: false,
      signUpWithEmail: vi.fn(),
      resendVerification: vi.fn(),
      signInWithEmail: vi.fn(),
      sendLoginCode: vi.fn(),
      verifyLoginCode: vi.fn(),
      sendPasswordReset: vi.fn(),
      setNewPassword: vi.fn(),
      signInWithGoogle: vi.fn(),
      verifyCurrentPassword: vi.fn(),
      changePassword: vi.fn(),
      signOut: vi.fn(),
    });
    mockUseMe.mockReturnValue({
      data: { user: { username: 'kvem_' }, needs_onboarding: false },
      isLoading: false,
    } as ReturnType<typeof useMe>);
    renderWithProviders(tree(), { route: '/play' });
    expect(screen.getByText('PLAY SCREEN')).toBeInTheDocument();
  });

  function signedIn(signOut = vi.fn()) {
    mockUseAuth.mockReturnValue({
      session: { user: { id: 'u1' } },
      loading: false,
      signOut,
    } as unknown as ReturnType<typeof useAuth>);
    return signOut;
  }

  it('keeps the session and offers a retry when the API is unreachable', async () => {
    const signOut = signedIn();
    const refetch = vi.fn();
    mockUseMe.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new TypeError('Failed to fetch'),
      refetch,
    } as unknown as ReturnType<typeof useMe>);
    renderWithProviders(tree(), { route: '/play' });

    expect(signOut).not.toHaveBeenCalled();
    screen.getByRole('button', { name: 'Try again' }).click();
    expect(refetch).toHaveBeenCalled();
  });

  it('keeps the page up when a background refresh fails', () => {
    const signOut = signedIn();
    mockUseMe.mockReturnValue({
      data: { user: { username: 'kvem_' }, needs_onboarding: false },
      isLoading: false,
      isError: true,
      error: new HttpError('Failed to load profile', 503),
    } as unknown as ReturnType<typeof useMe>);
    renderWithProviders(tree(), { route: '/play' });

    expect(signOut).not.toHaveBeenCalled();
    expect(screen.getByText('PLAY SCREEN')).toBeInTheDocument();
  });

  it('signs out when the API rejects the session', () => {
    const signOut = signedIn();
    mockUseMe.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new HttpError('Failed to load profile', 401),
    } as unknown as ReturnType<typeof useMe>);
    renderWithProviders(tree(), { route: '/play' });

    expect(signOut).toHaveBeenCalled();
  });
});
