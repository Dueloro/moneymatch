import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';

import { renderWithProviders } from '../test/testUtils';
import { AppShell } from './AppShell';

vi.mock('../hooks/useMe', () => ({ useMe: vi.fn() }));
// The live ticker depends on auth + query context the shell test doesn't provide.
vi.mock('./ui/Ticker', () => ({ Ticker: () => null }));
// The bell's badge is a live query (notifications + unread DMs); the shell test
// has no auth context, so drive it directly.
vi.mock('../hooks/useChat', () => ({ useInboxUnread: vi.fn(() => 0) }));

import { useInboxUnread } from '../hooks/useChat';
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

    // Nav renders in two responsive bars (desktop sidebar + mobile tab bar), so
    // a label can appear more than once; assert it is present at least once.
    for (const label of ['Activity', 'Social', 'Wallet']) {
      expect(screen.getAllByRole('link', { name: label }).length).toBeGreaterThan(0);
    }
    // The desktop sidebar uses full labels; the mobile bar abbreviates these.
    for (const label of ['Head-to-Head', 'Solo Pools', 'Tournament']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
    }
    expect(screen.getByText('PLAY CONTENT')).toBeInTheDocument();
    expect(screen.getByTestId('footer-breadcrumb')).toHaveTextContent('HEAD-TO-HEAD');
    expect(screen.getByText('kvem_')).toBeInTheDocument();
  });

  function renderShell() {
    return renderWithProviders(
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/play" element={<div>PLAY CONTENT</div>} />
        </Route>
      </Routes>,
      { route: '/play' },
    );
  }

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
    // Rendered by both responsive bars; the link carries the count for a11y.
    expect(screen.getAllByTestId('inbox-unread-dot').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: 'Inbox (2 unread)' }).length).toBe(2);
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
