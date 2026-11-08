import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { LinkGames } from './LinkGames';

const connectMutate = vi.fn();
const refreshMutate = vi.fn();

const UNLINKED = {
  game: 'chess.lichess',
  display_name: 'Chess',
  status: 'UNLINKED',
  host_username: null,
  linked_at: null,
  profile: null,
  win_streak: 0,
};

let games: Array<Record<string, unknown>> = [UNLINKED];

vi.mock('../hooks/useLinks', () => ({
  useLinks: () => ({ isLoading: false, isError: false, data: { games } }),
  useConnectLichess: () => ({ mutate: connectMutate, isPending: false, error: null }),
  useRefreshLink: () => ({ mutate: refreshMutate, isPending: false }),
}));

describe('LinkGames', () => {
  beforeEach(() => {
    connectMutate.mockClear();
    refreshMutate.mockClear();
    games = [UNLINKED];
  });

  it('shows one chess row with no game picker', () => {
    renderWithProviders(<LinkGames />);
    expect(screen.getByText('Chess')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('connects Lichess through OAuth, returning to the current page', async () => {
    window.history.replaceState(null, '', '/profile');
    const user = userEvent.setup();
    renderWithProviders(<LinkGames />);
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getByText(/not affiliated with lichess/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Connect Lichess' }));
    expect(connectMutate).toHaveBeenCalledWith('/profile');
  });

  it('shows the linked handle, rating, and a refresh action', async () => {
    games = [
      {
        ...UNLINKED,
        status: 'LINKED',
        host_username: 'magnus',
        profile: {
          rating: 2100,
          formats: [],
          primary_speed: 'blitz',
          total_games: 1234,
        },
      },
    ];
    const user = userEvent.setup();
    renderWithProviders(<LinkGames />);
    expect(screen.getByText('magnus · 1,234 games')).toBeInTheDocument();
    expect(screen.getByText('Rating 2100')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(refreshMutate).toHaveBeenCalledWith('chess.lichess');
  });
});
