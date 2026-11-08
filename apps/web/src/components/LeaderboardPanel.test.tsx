import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { LeaderboardPanel } from './LeaderboardPanel';

vi.mock('../hooks/useLeaderboard', async () => {
  const actual = await vi.importActual<typeof import('../hooks/useLeaderboard')>(
    '../hooks/useLeaderboard',
  );
  return { ...actual, useLeaderboard: vi.fn() };
});

import { useLeaderboard } from '../hooks/useLeaderboard';

function mock(data: unknown) {
  vi.mocked(useLeaderboard).mockReturnValue({ data } as ReturnType<
    typeof useLeaderboard
  >);
}

describe('LeaderboardPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows ROI rows with the you-row highlighted', () => {
    mock({
      rows: [
        {
          rank: 1,
          user_id: 'b',
          username: 'bob',
          roi_bps: 8000,
          net_cents: 2400,
          staked_cents: 3000,
          contests: 3,
          is_you: false,
        },
        {
          rank: 2,
          user_id: 'a',
          username: 'alice',
          roi_bps: -4000,
          net_cents: -1200,
          staked_cents: 3000,
          contests: 3,
          is_you: true,
        },
      ],
      you: { qualified: true, contests: 3, contests_needed: 0, row: null },
      window_days: 30,
      min_contests: 3,
    });
    renderWithProviders(<LeaderboardPanel />);
    expect(screen.getByText('+80.0%')).toBeInTheDocument();
    expect(screen.getByText('-40.0%')).toBeInTheDocument();
    expect(screen.getByText(/alice \(you\)/)).toBeInTheDocument();
  });

  it('nudges an unqualified viewer and empty-states an empty board', () => {
    mock({
      rows: [],
      you: { qualified: false, contests: 1, contests_needed: 2, row: null },
      window_days: 30,
      min_contests: 3,
    });
    renderWithProviders(<LeaderboardPanel />);
    expect(screen.getByText('Nobody is ranked yet')).toBeInTheDocument();
  });

  it('shows a skeleton while loading', () => {
    vi.mocked(useLeaderboard).mockReturnValue({ isLoading: true } as ReturnType<
      typeof useLeaderboard
    >);
    renderWithProviders(<LeaderboardPanel />);
    expect(screen.getByTestId('skeleton-list')).toBeInTheDocument();
  });

  it('shows an error with retry on failure', () => {
    const refetch = vi.fn();
    vi.mocked(useLeaderboard).mockReturnValue({
      isError: true,
      refetch,
    } as unknown as ReturnType<typeof useLeaderboard>);
    renderWithProviders(<LeaderboardPanel />);
    screen.getByRole('button', { name: 'Try again' }).click();
    expect(refetch).toHaveBeenCalled();
  });
});
