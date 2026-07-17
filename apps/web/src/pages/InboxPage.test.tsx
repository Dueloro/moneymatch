import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { InboxPage } from './InboxPage';

vi.mock('../hooks/useNotifications', () => ({
  useNotifications: vi.fn(),
  useMarkNotificationsRead: vi.fn(),
}));
vi.mock('../hooks/useChallenges', () => ({
  useAcceptChallenge: vi.fn(),
  useDeclineChallenge: vi.fn(),
}));

import { useAcceptChallenge, useDeclineChallenge } from '../hooks/useChallenges';
import { useMarkNotificationsRead, useNotifications } from '../hooks/useNotifications';

const markMutate = vi.fn();
const declineMutate = vi.fn();

describe('InboxPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useMarkNotificationsRead).mockReturnValue({
      mutate: markMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useMarkNotificationsRead>);
    vi.mocked(useAcceptChallenge).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useAcceptChallenge>);
    vi.mocked(useDeclineChallenge).mockReturnValue({
      mutate: declineMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useDeclineChallenge>);
  });

  it('renders a challenge notification with Respond and marks read on view', () => {
    vi.mocked(useNotifications).mockReturnValue({
      data: {
        unread: 1,
        items: [
          {
            id: 'n1',
            kind: 'challenge_received',
            payload: { challenge_id: 'c1', from_username: 'jordn_cs' },
            read: false,
            created_at: new Date().toISOString(),
          },
        ],
      },
    } as unknown as ReturnType<typeof useNotifications>);
    renderWithProviders(<InboxPage />);

    expect(screen.getByText(/jordn_cs challenged you/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Respond' })).toBeInTheDocument();
    // Mark-read fired on view (unread > 0).
    expect(markMutate).toHaveBeenCalledWith(undefined);

    fireEvent.click(screen.getByRole('button', { name: 'Decline' }));
    expect(declineMutate).toHaveBeenCalledWith('c1');
  });

  it('shows the empty state with no notifications', () => {
    vi.mocked(useNotifications).mockReturnValue({
      data: { unread: 0, items: [] },
    } as unknown as ReturnType<typeof useNotifications>);
    renderWithProviders(<InboxPage />);
    expect(screen.getByText('No notifications')).toBeInTheDocument();
  });
});
