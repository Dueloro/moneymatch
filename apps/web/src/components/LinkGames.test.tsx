import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { LinkGames } from './LinkGames';

const createMutate = vi.fn();
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
  useCreateLink: () => ({ mutate: createMutate, isPending: false }),
  useRefreshLink: () => ({ mutate: refreshMutate, isPending: false }),
}));

describe('LinkGames', () => {
  beforeEach(() => {
    createMutate.mockClear();
    refreshMutate.mockClear();
    games = [UNLINKED];
  });

  it('shows one chess row with no game picker', () => {
    renderWithProviders(<LinkGames />);
    expect(screen.getByText('Chess')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('links a Lichess username after a confirm step', async () => {
    const user = userEvent.setup();
    renderWithProviders(<LinkGames />);
    await user.click(screen.getByRole('button', { name: 'Link' }));
    await user.type(screen.getByPlaceholderText('Your Lichess username'), 'magnus');
    await user.click(screen.getByRole('button', { name: 'Verify' }));
    expect(createMutate).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Link account' }));
    expect(createMutate).toHaveBeenCalledWith(
      { game: 'chess.lichess', username: 'magnus' },
      expect.anything(),
    );
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
