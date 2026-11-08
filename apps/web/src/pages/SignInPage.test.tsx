import { useQuery } from '@tanstack/react-query';
import { screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { SignInPage } from './SignInPage';

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }));
vi.mock('../hooks/useMe', () => ({ useMe: vi.fn() }));
const connectMutate = vi.fn();
let linkedGames: { status: string }[] = [];
vi.mock('../hooks/useLinks', () => ({
  useLinks: () => ({ data: { games: linkedGames } }),
  useConnectLichess: () => ({ mutate: connectMutate, isPending: false, error: null }),
}));
vi.mock('../lib/api', () => ({ api: { PATCH: vi.fn() } }));

import { useAuth } from '../auth/useAuth';
import { useMe } from '../hooks/useMe';
import { api } from '../lib/api';

const mockUseAuth = vi.mocked(useAuth);
const mockUseMe = vi.mocked(useMe);

const signInWithEmail = vi.fn();
const signInWithGoogle = vi.fn();

describe('SignInPage', () => {
  beforeEach(() => {
    signInWithEmail.mockReset();
    signInWithGoogle.mockReset();
    mockUseAuth.mockReturnValue({
      session: null,
      loading: false,
      isPasswordRecovery: false,
      signUpWithEmail: vi.fn(),
      signInWithEmail,
      sendLoginCode: vi.fn(),
      verifyLoginCode: vi.fn(),
      sendPasswordReset: vi.fn(),
      setNewPassword: vi.fn(),
      signInWithGoogle,
      verifyCurrentPassword: vi.fn(),
      changePassword: vi.fn(),
      signOut: vi.fn(),
    });
    mockUseMe.mockReturnValue({ data: undefined, isLoading: false } as ReturnType<
      typeof useMe
    >);
  });

  it('renders email + password with Google options', () => {
    renderWithProviders(<SignInPage />, { route: '/signin' });
    expect(
      screen.getByRole('button', { name: /continue with google/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('signs in with email + password', async () => {
    signInWithEmail.mockResolvedValue(undefined);
    renderWithProviders(<SignInPage />, { route: '/signin' });
    await userEvent.type(screen.getByLabelText('Email'), 'kv@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'longenough');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(signInWithEmail).toHaveBeenCalledWith('kv@example.com', 'longenough');
  });

  it('starts the Google flow when the Google button is clicked', async () => {
    signInWithGoogle.mockResolvedValue(undefined);
    renderWithProviders(<SignInPage />, { route: '/signin' });
    await userEvent.click(
      screen.getByRole('button', { name: /continue with google/i }),
    );
    expect(signInWithGoogle).toHaveBeenCalledOnce();
  });

  it('shows no step progress on the sign-in form', () => {
    renderWithProviders(<SignInPage />, { route: '/signin' });
    expect(screen.queryByLabelText(/step \d of/i)).not.toBeInTheDocument();
  });

  it('has no email-code option (removed in favour of password / Google)', () => {
    renderWithProviders(<SignInPage />, { route: '/signin' });
    expect(
      screen.queryByRole('button', { name: /email me a code/i }),
    ).not.toBeInTheDocument();
  });

  it('pitches skill matching and API settlement', () => {
    renderWithProviders(<SignInPage />, { route: '/signin' });
    expect(
      screen.getByText(/matched with someone at your skill level/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no screenshots, no reviewers, no waiting/i),
    ).toBeInTheDocument();
    expect(screen.getByText('Points have no cash value.')).toBeInTheDocument();
  });

  it('links the legal footer to dueloro.com in a new tab', () => {
    renderWithProviders(<SignInPage />, { route: '/signin' });
    const terms = screen.getByRole('link', { name: 'Terms' });
    expect(terms).toHaveAttribute('href', 'https://www.dueloro.com/terms');
    expect(terms).toHaveAttribute('target', '_blank');
    expect(screen.getByRole('link', { name: 'Responsible Gaming' })).toHaveAttribute(
      'href',
      'https://www.dueloro.com/responsible-gaming',
    );
  });

  it('shows check-your-email after a signup that needs verification', async () => {
    const signUpWithEmail = vi.fn().mockResolvedValue({ needsVerification: true });
    mockUseAuth.mockReturnValue({
      ...mockUseAuth.mock.results[0]?.value,
      session: null,
      loading: false,
      isPasswordRecovery: false,
      signUpWithEmail,
      signInWithEmail,
      sendLoginCode: vi.fn(),
      verifyLoginCode: vi.fn(),
      sendPasswordReset: vi.fn(),
      setNewPassword: vi.fn(),
      signInWithGoogle,
      verifyCurrentPassword: vi.fn(),
      changePassword: vi.fn(),
      signOut: vi.fn(),
    });
    renderWithProviders(<SignInPage />, { route: '/signin' });
    await userEvent.click(screen.getByRole('button', { name: /^sign up$/i }));
    await userEvent.type(screen.getByLabelText('Email'), 'new@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'longenough');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText(/check your email/i)).toBeInTheDocument();
    expect(screen.getByText(/new@example.com/)).toBeInTheDocument();
  });

  it('requests a password reset email', async () => {
    const sendPasswordReset = vi.fn().mockResolvedValue(undefined);
    mockUseAuth.mockReturnValue({
      session: null,
      loading: false,
      isPasswordRecovery: false,
      signUpWithEmail: vi.fn(),
      signInWithEmail,
      sendLoginCode: vi.fn(),
      verifyLoginCode: vi.fn(),
      sendPasswordReset,
      setNewPassword: vi.fn(),
      signInWithGoogle,
      verifyCurrentPassword: vi.fn(),
      changePassword: vi.fn(),
      signOut: vi.fn(),
    });
    renderWithProviders(<SignInPage />, { route: '/signin' });
    await userEvent.click(screen.getByRole('button', { name: /forgot password/i }));
    await userEvent.type(screen.getByLabelText('Email'), 'kv@example.com');
    await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));
    expect(sendPasswordReset).toHaveBeenCalledWith('kv@example.com');
    expect(await screen.findByText(/check your email/i)).toBeInTheDocument();
  });

  it('shows set-new-password when in recovery', async () => {
    const setNewPassword = vi.fn().mockResolvedValue(undefined);
    mockUseAuth.mockReturnValue({
      session: { user: { id: 'u1' } } as never,
      loading: false,
      isPasswordRecovery: true,
      signUpWithEmail: vi.fn(),
      signInWithEmail,
      sendLoginCode: vi.fn(),
      verifyLoginCode: vi.fn(),
      sendPasswordReset: vi.fn(),
      setNewPassword,
      signInWithGoogle,
      verifyCurrentPassword: vi.fn(),
      changePassword: vi.fn(),
      signOut: vi.fn(),
    });
    mockUseMe.mockReturnValue({ data: undefined, isLoading: false } as ReturnType<
      typeof useMe
    >);
    renderWithProviders(<SignInPage />, { route: '/signin' });
    await userEvent.type(screen.getByLabelText(/new password/i), 'brandnew1');
    await userEvent.click(screen.getByRole('button', { name: /update password/i }));
    expect(setNewPassword).toHaveBeenCalledWith('brandnew1');
  });

  describe('a new invitee finishing setup', () => {
    let needsOnboarding: boolean;

    beforeEach(() => {
      sessionStorage.clear();
      connectMutate.mockClear();
      linkedGames = [];
      needsOnboarding = true;
      mockUseAuth.mockReturnValue({
        session: { user: { id: 'u1' } } as never,
        loading: false,
        isPasswordRecovery: false,
      } as unknown as ReturnType<typeof useAuth>);
      mockUseMe.mockImplementation(
        () =>
          ({
            data: { needs_onboarding: needsOnboarding, user: { username: null } },
            isLoading: false,
            isError: false,
          }) as unknown as ReturnType<typeof useMe>,
      );
      vi.mocked(api.PATCH).mockImplementation(async () => {
        needsOnboarding = false;
        return { data: {}, error: undefined } as never;
      });
    });

    function renderFlow() {
      renderWithProviders(
        <Routes>
          <Route path="/signin" element={<SignInPage />} />
          <Route path="/i/:token" element={<p>invite preview</p>} />
          <Route path="/play" element={<p>play page</p>} />
        </Routes>,
        { route: '/signin' },
      );
    }

    async function finishProfile() {
      expect(screen.getByLabelText(/step 1 of 2/i)).toBeInTheDocument();
      await userEvent.type(screen.getByPlaceholderText('player_name'), 'new_player');
      await userEvent.selectOptions(screen.getByRole('combobox'), 'NY');
      await userEvent.click(screen.getByRole('checkbox'));
      await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    }

    async function finishProfileAndEnter() {
      await finishProfile();
      await userEvent.click(
        await screen.findByRole('button', { name: 'Skip for now' }),
      );
    }

    it('makes Connect Lichess the one action and carries the invite through', async () => {
      sessionStorage.setItem('mm.returnTo', '/i/tok123');
      window.history.replaceState(null, '', '/signin');
      renderFlow();
      await finishProfile();
      expect(await screen.findByLabelText(/step 2 of 2/i)).toBeInTheDocument();
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole('button', { name: 'Connect Lichess' }));
      expect(connectMutate).toHaveBeenCalledWith('/i/tok123');
      window.history.replaceState(null, '', '/');
    });

    it('reaches the link step with a real profile refetch', async () => {
      mockUseMe.mockImplementation(
        () =>
          useQuery({
            queryKey: ['me'],
            queryFn: async () => ({
              needs_onboarding: needsOnboarding,
              user: { username: null },
            }),
          }) as unknown as ReturnType<typeof useMe>,
      );
      renderFlow();
      await screen.findByPlaceholderText('player_name');
      await finishProfile();
      expect(
        await screen.findByRole('button', { name: 'Connect Lichess' }),
      ).toBeInTheDocument();
      expect(screen.queryByText('play page')).not.toBeInTheDocument();
    });

    it('skips the link step when Lichess is already linked', async () => {
      linkedGames = [{ status: 'LINKED' }];
      renderFlow();
      await finishProfile();
      expect(await screen.findByText('play page')).toBeInTheDocument();
    });

    it('lands back on the invite it came from, once', async () => {
      sessionStorage.setItem('mm.returnTo', '/i/tok123');
      renderFlow();
      await finishProfileAndEnter();
      expect(await screen.findByText('invite preview')).toBeInTheDocument();
      expect(sessionStorage.getItem('mm.returnTo')).toBeNull();
    });

    it('goes to Play when there is no pending invite', async () => {
      renderFlow();
      await finishProfileAndEnter();
      expect(await screen.findByText('play page')).toBeInTheDocument();
    });
  });
});
