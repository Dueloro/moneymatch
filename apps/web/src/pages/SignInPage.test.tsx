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

const signInWithUsername = vi.fn();
const signInWithGoogle = vi.fn();

describe('SignInPage', () => {
  beforeEach(() => {
    signInWithUsername.mockReset();
    signInWithGoogle.mockReset();
    mockUseAuth.mockReturnValue({
      session: null,
      loading: false,
      signInWithUsername,
      signUpWithUsername: vi.fn(),
      signInWithGoogle,
      verifyCurrentPassword: vi.fn(),
      changePassword: vi.fn(),
      isDemo: false,
      signOut: vi.fn(),
    });
    mockUseMe.mockReturnValue({ data: undefined, isLoading: false } as ReturnType<
      typeof useMe
    >);
  });

  it('renders the auth step with Google, username + password, and demo options', () => {
    renderWithProviders(<SignInPage />, { route: '/signin' });
    expect(
      screen.getByRole('button', { name: /continue with google/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Username')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /enter the demo/i })).toBeInTheDocument();
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

  it('keeps the submit button clickable and explains an invalid username instead of a dead button', async () => {
    renderWithProviders(<SignInPage />, { route: '/signin' });
    // A too-long username that fails ^[a-z0-9_]{3,20}$.
    await userEvent.type(
      screen.getByLabelText('Username'),
      'this_name_is_way_too_long',
    );
    await userEvent.type(screen.getByLabelText('Password'), 'longenough');

    const submit = screen.getByRole('button', { name: 'Sign in' });
    expect(submit).toBeEnabled();
    await userEvent.click(submit);

    // The auth call is never attempted; the user gets a specific reason instead.
    expect(signInWithUsername).not.toHaveBeenCalled();
    expect(screen.getByText(/20 characters or fewer/i)).toBeInTheDocument();
  });

  it('submits when the username and password are valid', async () => {
    signInWithUsername.mockResolvedValue(undefined);
    renderWithProviders(<SignInPage />, { route: '/signin' });
    await userEvent.type(screen.getByLabelText('Username'), 'kvem_');
    await userEvent.type(screen.getByLabelText('Password'), 'longenough');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(signInWithUsername).toHaveBeenCalledWith('kvem_', 'longenough');
  });
});
