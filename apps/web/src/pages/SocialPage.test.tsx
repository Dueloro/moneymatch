import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { useInboxBadge } from '../hooks/useInbox';
import { SocialPage } from './SocialPage';

const { server, apiGet, apiPost } = vi.hoisted(() => {
  const server = { badge: 3, release: () => {} };
  return {
    server,
    apiGet: vi.fn(async () => ({ data: { badge: server.badge }, error: undefined })),
    apiPost: vi.fn(
      () =>
        new Promise<{ data: unknown; error: unknown }>((resolve) => {
          server.release = () => {
            server.badge = 0;
            resolve({ data: { badge: 0 }, error: undefined });
          };
        }),
    ),
  };
});

vi.mock('../lib/api', () => ({ api: { GET: apiGet, POST: apiPost } }));
vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ session: { user: { id: 'u1' } } }),
}));
vi.mock('../hooks/useChat', () => ({ useInboxUnread: () => 2 }));
vi.mock('./InboxPage', () => ({ InboxPage: () => <div>inbox</div> }));
vi.mock('../components/FriendsPanel', () => ({ FriendsPanel: () => null }));
vi.mock('../components/LeaderboardPanel', () => ({ LeaderboardPanel: () => null }));

function NavBadge() {
  return <span data-testid="nav-badge">{useInboxBadge()}</span>;
}

describe('SocialPage', () => {
  it('opening Social clears the nav badge at once; the Inbox tab keeps its unread', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const Wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/social?tab=leaderboard']}>
          {children}
        </MemoryRouter>
      </QueryClientProvider>
    );
    const { rerender } = render(<NavBadge />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByTestId('nav-badge')).toHaveTextContent('3'));

    rerender(
      <>
        <NavBadge />
        <SocialPage />
      </>,
    );

    // Optimistic: the badge drops before the server answers.
    await waitFor(() => expect(screen.getByTestId('nav-badge')).toHaveTextContent('0'));
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/v1/inbox/seen'));
    expect(screen.getByRole('tab', { name: /Inbox/ })).toHaveTextContent('2');

    await act(async () => server.release());
    await waitFor(() => expect(screen.getByTestId('nav-badge')).toHaveTextContent('0'));
    expect(apiPost).toHaveBeenCalledTimes(1);
  });
});
