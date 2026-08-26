import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';

import { renderWithProviders } from '../test/testUtils';
import { AppShell } from './AppShell';

vi.mock('../hooks/useMe', () => ({ useMe: vi.fn() }));
// The live ticker depends on auth + query context the shell test doesn't provide.
vi.mock('./ui/Ticker', () => ({ Ticker: () => null }));
// Same for the rail, which reads wallet + activity + queue.
vi.mock('./rail/SideRail', () => ({ SideRail: () => null }));
// The SSE listener needs the auth + query context the shell test doesn't provide.
vi.mock('../hooks/useEventStream', () => ({ useEventStream: () => {} }));
// Same for the settlement result overlay, which reads Activity. Its own
// behaviour is covered in SettlementCelebration.test.tsx.
vi.mock('./SettlementCelebration', () => ({ SettlementCelebration: () => null }));
vi.mock('../hooks/useWallet', () => ({
  useWallet: () => ({ data: { available_cents: 100_800, escrow_cents: 0 } }),
}));
// The bell's badge is a live query (notifications + unread DMs); the shell test
// has no auth context, so drive it directly.
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

    // Six entries collapsed to four: the three contest modes live behind "Play"
    // with a mode switcher on that surface. Nav renders in two responsive bars
    // (desktop sidebar + mobile tab bar), so a label appears more than once.
    for (const label of ['Play', 'Activity', 'Social', 'Wallet']) {
      expect(screen.getAllByRole('link', { name: label }).length).toBe(2);
    }
    // Tournament and Head-to-Head are no longer top-level nav entries.
    expect(screen.queryByRole('link', { name: 'Tournament' })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Head-to-Head' }),
    ).not.toBeInTheDocument();

    expect(screen.getByText('POOLS CONTENT')).toBeInTheDocument();
    expect(screen.getByText('kvem_')).toBeInTheDocument();
  });

  it('keeps Play lit on every contest route', () => {
    renderShell('/play');
    const play = screen.getAllByRole('link', { name: 'Play' });
    // `aria-current` is what NavLink sets for the active entry.
    expect(play.some((el) => el.getAttribute('aria-current') === 'page')).toBe(true);
    expect(screen.getByText('PLAY CONTENT')).toBeInTheDocument();
  });

  it('shows the balance in the sidebar footer', () => {
    renderShell();
    // The sidebar's dead space now ends in the number players check first.
    expect(screen.getAllByText('$1,008.00').length).toBeGreaterThan(0);
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
