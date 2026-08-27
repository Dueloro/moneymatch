import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useGameSelection } from './useGameSelection';

// The full catalog the links endpoint returns (all four games, regardless of
// whether they're in the player's play set).
const CATALOG = [
  { game: 'chess.lichess', status: 'UNLINKED' },
  { game: 'cs2.steam', status: 'LINKED' },
  { game: 'pubg.steam', status: 'UNLINKED' },
  { game: 'dota2.opendota', status: 'UNLINKED' },
];

let activeGames: string[] = [];

vi.mock('./useLinks', () => ({
  useLinks: () => ({ data: { games: CATALOG } }),
}));
vi.mock('./useMe', () => ({
  useMe: () => ({ data: { user: { active_games: activeGames } } }),
}));

function ids() {
  return renderHook(() => useGameSelection()).result.current.games.map((g) => g.game);
}

describe('useGameSelection — strict, fail-closed gating', () => {
  beforeEach(() => {
    window.localStorage.clear?.();
    activeGames = [];
  });

  it('a Chess-only play set shows Chess and nothing else', () => {
    activeGames = ['chess.lichess'];
    const games = ids();
    expect(games).toEqual(['chess.lichess']);
    // Zero trace of the other three anywhere in the switcher-driving list.
    for (const hidden of ['cs2.steam', 'pubg.steam', 'dota2.opendota']) {
      expect(games).not.toContain(hidden);
    }
  });

  it('an empty play set fails closed to Chess only — not every game', () => {
    activeGames = [];
    expect(ids()).toEqual(['chess.lichess']);
  });

  it('an explicit multi-game set shows exactly those games', () => {
    activeGames = ['cs2.steam', 'chess.lichess'];
    const games = ids();
    expect(new Set(games)).toEqual(new Set(['cs2.steam', 'chess.lichess']));
    expect(games).not.toContain('pubg.steam');
    expect(games).not.toContain('dota2.opendota');
  });

  it('corrects the persisted selection when the active game is removed via Profile', () => {
    activeGames = ['cs2.steam', 'chess.lichess'];
    const { result, rerender } = renderHook(() => useGameSelection());
    act(() => result.current.select('cs2.steam'));
    expect(result.current.selected).toBe('cs2.steam');

    // Profile removes CS2 → the active set shrinks on the next /me. The hook's
    // effect must drop the now-hidden selection to a still-visible game.
    activeGames = ['chess.lichess'];
    rerender();
    expect(result.current.selected).toBe('chess.lichess');
  });
});
