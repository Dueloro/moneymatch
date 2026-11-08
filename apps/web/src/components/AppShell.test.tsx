import { screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';

import { renderWithProviders } from '../test/testUtils';
import { AppShell } from './AppShell';

vi.mock('../hooks/useMe', () => ({ useMe: vi.fn() }));
vi.mock('./ui/Ticker', () => ({ Ticker: () => null }));
vi.mock('./rail/SideRail', () => ({ SideRail: () => null }));
// The SSE listener needs the auth + query context the shell test doesn't
// provide.
vi.mock('../hooks/useEventStream', () => ({ useEventStream: () => {} }));
vi.mock('./SettlementCelebration', () => ({ SettlementCelebration: () => null }));
vi.mock('./SettlementProvider', () => ({
  SettlementProvider: ({ children }: { children: ReactNode }) => children,
  useSettlement: () => ({ current: null, dismiss: () => {} }),
}));
vi.mock('../hooks/useWallet', () => ({
  useWallet: () => ({ data: { available_cents: 100_800, escrow_cents: 0 } }),
}));
vi.mock('../hooks/useChat', () => ({ useInboxUnread: vi.fn(() => 0) }));

import { useInboxUnread } from '../hooks/useChat';
import { useMe } from '../hooks/useMe';

vi.mocked(useMe).mockReturnValue({
  data: { user: { username: 'kvem_' }, needs_onboarding: false },
  isLoading: false,
} as ReturnType<typeof useMe>);

function renderShell(route = '/pools') {
  return renderWithProviders(
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/pools" element={<div>POOLS CONTENT</div>} />
        <Route path="/play" element={<div>PLAY CONTENT</div>} />
      </Route>
    </Routes>,
    { route },
  );
}

describe('AppShell', () => {
  it('renders four primary nav entries and the routed content', () => {
    renderShell();

    for (const label of ['Play', 'Activity', 'Social', 'Wallet']) {
      expect(screen.getAllByRole('link', { name: label }).length).toBe(2);
    }
    expect(screen.queryByRole('link', { name: 'Tournament' })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Head-to-Head' }),
    ).not.toBeInTheDocument();

    expect(screen.getByText('POOLS CONTENT')).toBeInTheDocument();
    expect(screen.getByText('kvem_')).toBeInTheDocument();
  });

  it('points Play and the logo at /play, the one home', () => {
    renderShell();
    for (const el of screen.getAllByRole('link', { name: 'Play' })) {
      expect(el).toHaveAttribute('href', '/play');
    }
    for (const el of screen.getAllByRole('link', { name: 'Money Match home' })) {
      expect(el).toHaveAttribute('href', '/play');
    }
  });

  it('keeps Play lit on every contest route', () => {
    renderShell('/pools');
    const play = screen.getAllByRole('link', { name: 'Play' });
    expect(play.some((el) => el.getAttribute('aria-current') === 'page')).toBe(true);
    expect(screen.getByText('POOLS CONTENT')).toBeInTheDocument();
  });

  it('shows the balance in the sidebar footer', () => {
    renderShell();
    expect(screen.getByTestId('sidebar-balance')).toHaveTextContent('100,800 pts');
  });

  it('shows a role-gated Admin link for admins', () => {
    vi.mocked(useMe).mockReturnValue({
      data: { user: { username: 'ops', role: 'admin' }, needs_onboarding: false },
      isLoading: false,
    } as ReturnType<typeof useMe>);
    renderShell();
    expect(screen.getByRole('link', { name: 'Admin' })).toHaveAttribute(
      'href',
      '/admin',
    );
  });

  it('lights the bell for an unread message from anywhere in the app', () => {
    vi.mocked(useMe).mockReturnValue({
      data: { user: { username: 'kvem_' }, needs_onboarding: false },
      isLoading: false,
    } as ReturnType<typeof useMe>);

    vi.mocked(useInboxUnread).mockReturnValue(0);
    renderShell().unmount();
    expect(screen.queryByTestId('inbox-unread-dot')).not.toBeInTheDocument();

    vi.mocked(useInboxUnread).mockReturnValue(2);
    renderShell();
    expect(screen.getByTestId('inbox-unread-dot')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Inbox, 2 unread' })).toBeInTheDocument();
  });

  it('hides the Admin link from non-admins', () => {
    vi.mocked(useMe).mockReturnValue({
      data: { user: { username: 'kvem_', role: 'user' }, needs_onboarding: false },
      isLoading: false,
    } as ReturnType<typeof useMe>);
    renderShell();
    expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument();
  });
});
