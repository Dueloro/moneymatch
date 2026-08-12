import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { SignInPage } from './SignInPage';

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }));
vi.mock('../hooks/useMe', () => ({ useMe: vi.fn() }));

import { useAuth } from '../auth/useAuth';
import { useMe } from '../hooks/useMe';

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
      isDemo: false,
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

  it('renders email + password with Google and demo options', () => {
    renderWithProviders(<SignInPage />, { route: '/signin' });
    expect(
      screen.getByRole('button', { name: /continue with google/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /enter the demo/i })).toBeInTheDocument();
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

  it('shows the 3-step progress bar', () => {
    renderWithProviders(<SignInPage />, { route: '/signin' });
    expect(screen.getByLabelText(/step 1 of 3/i)).toBeInTheDocument();
  });

  it('sends and verifies an email login code', async () => {
    const sendLoginCode = vi.fn().mockResolvedValue(undefined);
    const verifyLoginCode = vi.fn().mockResolvedValue(undefined);
    mockUseAuth.mockReturnValue({
      session: null,
      loading: false,
      isDemo: false,
      isPasswordRecovery: false,
      signUpWithEmail: vi.fn(),
      signInWithEmail,
      sendLoginCode,
      verifyLoginCode,
      sendPasswordReset: vi.fn(),
      setNewPassword: vi.fn(),
      signInWithGoogle,
      verifyCurrentPassword: vi.fn(),
      changePassword: vi.fn(),
      signOut: vi.fn(),
    });
    renderWithProviders(<SignInPage />, { route: '/signin' });
    await userEvent.click(screen.getByRole('button', { name: /email me a code/i }));
    await userEvent.type(screen.getByLabelText('Email'), 'kv@example.com');
    await userEvent.click(screen.getByRole('button', { name: /send code/i }));
    expect(sendLoginCode).toHaveBeenCalledWith('kv@example.com');
    await userEvent.type(await screen.findByLabelText(/code/i), '123456');
    await userEvent.click(screen.getByRole('button', { name: /verify/i }));
    expect(verifyLoginCode).toHaveBeenCalledWith('kv@example.com', '123456');
  });

  it('shows check-your-email after a signup that needs verification', async () => {
    const signUpWithEmail = vi.fn().mockResolvedValue({ needsVerification: true });
    mockUseAuth.mockReturnValue({
      ...mockUseAuth.mock.results[0]?.value,
      session: null,
      loading: false,
      isDemo: false,
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
    await userEvent.click(screen.getByRole('button', { name: /create an account/i }));
    await userEvent.type(screen.getByLabelText('Email'), 'new@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'longenough');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText(/check your email/i)).toBeInTheDocument();
    expect(screen.getByText(/new@example.com/)).toBeInTheDocument();
  });
});
