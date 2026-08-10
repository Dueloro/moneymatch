import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { NotificationsFeed } from './NotificationsFeed';

vi.mock('../hooks/useNotifications', () => ({
  useNotifications: vi.fn(),
  useMarkNotificationsRead: vi.fn(),
}));
vi.mock('../hooks/useChallenges', () => ({
  useAcceptChallenge: vi.fn(),
  useDeclineChallenge: vi.fn(),
}));
vi.mock('../hooks/usePools', () => ({ usePool: vi.fn() }));
vi.mock('../hooks/useTournaments', () => ({ useTournament: vi.fn() }));

import { useAcceptChallenge, useDeclineChallenge } from '../hooks/useChallenges';
import { useMarkNotificationsRead, useNotifications } from '../hooks/useNotifications';
import { usePool } from '../hooks/usePools';
import { useTournament } from '../hooks/useTournaments';

const markMutate = vi.fn();
const declineMutate = vi.fn();

function feed(items: unknown[]) {
  vi.mocked(useNotifications).mockReturnValue({
    data: { unread: 0, items },
  } as unknown as ReturnType<typeof useNotifications>);
}

const POOL_NOTE = {
  id: 'n2',
  kind: 'room_filled',
  payload: { kind: 'pool', pool_id: 'p1' },
  read: true,
  created_at: new Date().toISOString(),
};

const TOURNAMENT_NOTE = {
  id: 'n3',
  kind: 'settled',
  payload: { kind: 'tournament', tournament_id: 't1' },
  read: true,
  created_at: new Date().toISOString(),
};

function poolData(over: Record<string, unknown> = {}) {
  return {
    data: {
      id: 'p1',
      metric: 'chess_moves',
      metric_label: 'Moves to win',
      difficulty: 'hard',
      room_bar: 12,
      entry_cents: 2500,
      pot_cents: 10000,
      state: 'LOCKED',
      members: [
        {
          user_id: 'u1',
          username: 'demo',
          personal_bar: 12,
          status: 'LOCKED',
          payout_cents: 0,
          is_you: true,
          result_value: null,
        },
        {
          user_id: 'u2',
          username: 'testbot_ada',
          personal_bar: 12,
          status: 'LOCKED',
          payout_cents: 0,
          is_you: false,
          result_value: null,
        },
      ],
      ...over,
    },
    isPending: false,
    isError: false,
  } as unknown as ReturnType<typeof usePool>;
}

describe('NotificationsFeed', () => {
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
    renderWithProviders(<NotificationsFeed />);

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
    renderWithProviders(<NotificationsFeed />);
    expect(screen.getByText('No notifications')).toBeInTheDocument();
  });

  it('opens a filled pool room to show who is in it', () => {
    feed([POOL_NOTE]);
    vi.mocked(usePool).mockReturnValue(poolData());
    renderWithProviders(<NotificationsFeed />);

    // Collapsed: the roster is not fetched or rendered yet.
    expect(screen.queryByText('testbot_ada')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Your pool room filled/ }));
    expect(screen.getByText('demo (you)')).toBeInTheDocument();
    expect(screen.getByText('testbot_ada')).toBeInTheDocument();
    expect(screen.getByText(/Moves to win · hard/)).toBeInTheDocument();
  });

  it('shows both sides of a settled room, clearer first', () => {
    feed([{ ...POOL_NOTE, kind: 'settled' }]);
    vi.mocked(usePool).mockReturnValue(
      poolData({
        state: 'SETTLED',
        members: [
          {
            user_id: 'u2',
            username: 'testbot_ada',
            personal_bar: 12,
            status: 'MISSED',
            payout_cents: 0,
            is_you: false,
            result_value: null,
          },
          {
            user_id: 'u1',
            username: 'demo',
            personal_bar: 12,
            status: 'CLEARED',
            payout_cents: 9000,
            is_you: true,
            result_value: 8,
          },
        ],
      }),
    );
    renderWithProviders(<NotificationsFeed />);
    fireEvent.click(screen.getByRole('button', { name: /A contest settled/ }));

    // The winner's own number, worded for a fewest-is-better metric.
    expect(screen.getByText(/in 8 · bar 12/)).toBeInTheDocument();
    expect(screen.getByText('Cleared')).toBeInTheDocument();
    expect(screen.getByText('Missed')).toBeInTheDocument();
    expect(screen.getByText('+$90.00')).toBeInTheDocument();

    // Cleared is listed above missed regardless of the order the API returned.
    const rows = screen.getAllByText(/demo \(you\)|testbot_ada/);
    expect(rows[0]).toHaveTextContent('demo');
  });

  it('opens a tournament to show the ranking', () => {
    feed([TOURNAMENT_NOTE]);
    vi.mocked(useTournament).mockReturnValue({
      data: {
        id: 't1',
        metric: 'chess_wins',
        metric_label: 'Total wins',
        entry_cents: 2500,
        pot_cents: 25000,
        state: 'SETTLED',
        standings: [
          {
            user_id: 'u1',
            username: 'demo',
            score: 3,
            matches: 3,
            rank: 1,
            is_you: true,
            payout_cents: 11250,
          },
          {
            user_id: 'u2',
            username: 'testbot_ada',
            score: 0,
            matches: 0,
            rank: 2,
            is_you: false,
            payout_cents: 0,
          },
        ],
      },
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof useTournament>);
    renderWithProviders(<NotificationsFeed />);
    fireEvent.click(screen.getByRole('button', { name: /A contest settled/ }));

    expect(screen.getByText('#1 demo (you)')).toBeInTheDocument();
    expect(screen.getByText('#2 testbot_ada')).toBeInTheDocument();
    expect(screen.getByText('3 · 3 matches')).toBeInTheDocument();
    expect(screen.getByText('+$112.50')).toBeInTheDocument();
  });

  it('leaves a non-contest notification unexpandable', () => {
    feed([
      {
        id: 'n4',
        kind: 'friend_request',
        payload: { from_username: 'kvem_' },
        read: true,
        created_at: new Date().toISOString(),
      },
    ]);
    renderWithProviders(<NotificationsFeed />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
