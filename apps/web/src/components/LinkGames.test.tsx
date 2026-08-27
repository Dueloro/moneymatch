import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { LinkGames } from './LinkGames';

const setActiveGames = vi.fn();
const createMutate = vi.fn();
const refreshMutate = vi.fn();

let activeGames: string[] = ['chess.lichess'];

const CATALOG = [
  {
    game: 'chess.lichess',
    display_name: 'Chess',
    status: 'UNLINKED',
    host_username: null,
    linked_at: null,
    profile: null,
    win_streak: 0,
  },
  {
    game: 'cs2.steam',
    display_name: 'CS2',
    status: 'UNLINKED',
    host_username: null,
    linked_at: null,
    profile: null,
    win_streak: 0,
  },
  {
    game: 'pubg.steam',
    display_name: 'PUBG',
    status: 'UNLINKED',
    host_username: null,
    linked_at: null,
    profile: null,
    win_streak: 0,
  },
  {
    game: 'dota2.opendota',
    display_name: 'Dota 2',
    status: 'UNLINKED',
    host_username: null,
    linked_at: null,
    profile: null,
    win_streak: 0,
  },
];

vi.mock('../hooks/useLinks', () => ({
  useLinks: () => ({ isLoading: false, isError: false, data: { games: CATALOG } }),
  useCreateLink: () => ({ mutate: createMutate, isPending: false }),
  useRefreshLink: () => ({ mutate: refreshMutate, isPending: false }),
}));
vi.mock('../hooks/useMe', () => ({
  useMe: () => ({ data: { user: { active_games: activeGames } } }),
  useSetActiveGames: () => ({ mutate: setActiveGames, isPending: false }),
}));

function checkbox(name: RegExp) {
  return screen.getByRole('checkbox', { name });
}

describe('LinkGames — availability-aware add/remove', () => {
  beforeEach(() => {
    setActiveGames.mockClear();
    createMutate.mockClear();
    refreshMutate.mockClear();
    activeGames = ['chess.lichess'];
  });

  describe('production', () => {
    it('locks CS2/PUBG/Dota (disabled) and keeps Chess always-on', () => {
      renderWithProviders(<LinkGames context="production" />);
      expect(checkbox(/Chess \(always on\)/)).toBeDisabled();
      expect(checkbox(/Counter-Strike 2 \(available after launch\)/)).toBeDisabled();
      expect(checkbox(/PUBG \(available after launch\)/)).toBeDisabled();
      expect(checkbox(/Dota 2 \(coming soon\)/)).toBeDisabled();
    });

    it('does not add a locked game when its (disabled) toggle is clicked', async () => {
      const user = userEvent.setup();
      renderWithProviders(<LinkGames context="production" />);
      await user.click(checkbox(/Counter-Strike 2/));
      expect(setActiveGames).not.toHaveBeenCalled();
    });
  });

  describe('demo', () => {
    it('lets CS2 be added (writes the enlarged set)', async () => {
      const user = userEvent.setup();
      renderWithProviders(<LinkGames context="demo" />);
      const cs2 = checkbox(/Add Counter-Strike 2/);
      expect(cs2).not.toBeDisabled();
      await user.click(cs2);
      expect(setActiveGames).toHaveBeenCalledWith(['chess.lichess', 'cs2.steam']);
    });

    it('lets Dota 2 be added despite its SOON badge', async () => {
      const user = userEvent.setup();
      renderWithProviders(<LinkGames context="demo" />);
      const dota = checkbox(/Add Dota 2/);
      expect(dota).not.toBeDisabled();
      await user.click(dota);
      expect(setActiveGames).toHaveBeenCalledWith(['chess.lichess', 'dota2.opendota']);
    });

    it('removes an active game by writing the set without it — no delete/unlink', async () => {
      const user = userEvent.setup();
      activeGames = ['chess.lichess', 'cs2.steam'];
      renderWithProviders(<LinkGames context="demo" />);
      await user.click(checkbox(/Remove Counter-Strike 2/));
      expect(setActiveGames).toHaveBeenCalledWith(['chess.lichess']);
      // Removal is a play-set edit only — it never touches the link record.
      expect(createMutate).not.toHaveBeenCalled();
      expect(refreshMutate).not.toHaveBeenCalled();
    });

    it('never lets Chess be removed', async () => {
      const user = userEvent.setup();
      activeGames = ['chess.lichess', 'cs2.steam'];
      renderWithProviders(<LinkGames context="demo" />);
      await user.click(checkbox(/Chess \(always on\)/));
      expect(setActiveGames).not.toHaveBeenCalled();
    });
  });
});
