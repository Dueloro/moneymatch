import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';

import { renderWithProviders } from '../test/testUtils';
import { AppShell } from './AppShell';

vi.mock('../hooks/useMe', () => ({ useMe: vi.fn() }));

import { useMe } from '../hooks/useMe';

vi.mocked(useMe).mockReturnValue({
  data: { user: { username: 'kvem_' }, needs_onboarding: false },
  isLoading: false,
} as ReturnType<typeof useMe>);

describe('AppShell', () => {
  it('renders the sidebar nav, routed content, and footer breadcrumb', () => {
    renderWithProviders(
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/play" element={<div>PLAY CONTENT</div>} />
        </Route>
      </Routes>,
      { route: '/play' },
    );

    for (const label of ['Play', 'Pools', 'Tournament', 'Activity', 'Wallet']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
    }
    expect(screen.getByText('PLAY CONTENT')).toBeInTheDocument();
    expect(screen.getByTestId('footer-breadcrumb')).toHaveTextContent('PLAY');
    expect(screen.getByText('kvem_')).toBeInTheDocument();
  });
});
