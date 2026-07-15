import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';

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
      signInWithGoogle: vi.fn(),
      signInWithEmail: vi.fn(),
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
      signInWithGoogle: vi.fn(),
      signInWithEmail: vi.fn(),
      signOut: vi.fn(),
    });
    mockUseMe.mockReturnValue({
      data: { user: { username: 'kvem_' }, needs_onboarding: false },
      isLoading: false,
    } as ReturnType<typeof useMe>);
    renderWithProviders(tree(), { route: '/play' });
    expect(screen.getByText('PLAY SCREEN')).toBeInTheDocument();
  });
});
