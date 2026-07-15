import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { SignInPage } from './SignInPage';

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }));
vi.mock('../hooks/useMe', () => ({ useMe: vi.fn() }));

import { useAuth } from '../auth/useAuth';
import { useMe } from '../hooks/useMe';

const mockUseAuth = vi.mocked(useAuth);
const mockUseMe = vi.mocked(useMe);

describe('SignInPage', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      session: null,
      loading: false,
      signInWithGoogle: vi.fn(),
      signInWithEmail: vi.fn(),
      signOut: vi.fn(),
    });
    mockUseMe.mockReturnValue({ data: undefined, isLoading: false } as ReturnType<
      typeof useMe
    >);
  });

  it('renders the auth step with Google and email options', () => {
    renderWithProviders(<SignInPage />, { route: '/signin' });
    expect(
      screen.getByRole('button', { name: /continue with google/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /continue with email/i }),
    ).toBeInTheDocument();
  });

  it('shows the 3-step progress bar', () => {
    renderWithProviders(<SignInPage />, { route: '/signin' });
    expect(screen.getByLabelText(/step 1 of 3/i)).toBeInTheDocument();
  });
});
