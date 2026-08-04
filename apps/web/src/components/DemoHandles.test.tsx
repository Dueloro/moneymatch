import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';

vi.mock('../hooks/useLinks', async () => {
  const actual =
    await vi.importActual<typeof import('../hooks/useLinks')>('../hooks/useLinks');
  return { ...actual, useLinks: vi.fn(), useDemoRelink: vi.fn() };
});

import { DemoHandles } from './DemoHandles';
import { useDemoRelink, useLinks, type GameLink } from '../hooks/useLinks';

const relinkMutate = vi.fn();

function gameLink(over: Partial<GameLink>): GameLink {
  return {
    game: 'chess.lichess',
    display_name: 'Chess — Lichess',
    status: 'LINKED',
    host_username: 'demo',
    linked_at: null,
    profile: null,
    win_streak: 0,
    ...over,
  };
}

describe('DemoHandles', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useDemoRelink).mockReturnValue({
      mutate: relinkMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useDemoRelink>);
    vi.mocked(useLinks).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        games: [
          gameLink({ game: 'chess.lichess', display_name: 'Chess — Lichess' }),
          gameLink({
            game: 'pubg.steam',
            display_name: 'PUBG — Steam',
            host_username: 'demo',
          }),
          gameLink({
            game: 'valorant.riot',
            display_name: 'Valorant — Riot',
            status: 'COMING_SOON',
          }),
        ],
      },
    } as unknown as ReturnType<typeof useLinks>);
  });

  it('lists a row per playable game with its current handle', () => {
    renderWithProviders(<DemoHandles />);
    // Rows use the canonical gameMeta name, matching the rest of the app.
    expect(screen.getByText('Chess')).toBeInTheDocument();
    expect(screen.getByText('PUBG')).toBeInTheDocument();
    // Coming-soon games have no adapter, so no handle-swap row.
    expect(screen.queryByText('Valorant')).not.toBeInTheDocument();
  });

  it('submits the typed real handle for the right game', () => {
    renderWithProviders(<DemoHandles />);
    const inputs = screen.getAllByPlaceholderText(/real username/i);
    fireEvent.change(inputs[0], { target: { value: 'DrNykterstein' } });
    fireEvent.click(screen.getAllByRole('button', { name: /save/i })[0]);
    expect(relinkMutate).toHaveBeenCalledWith(
      expect.objectContaining({ game: 'chess.lichess', username: 'DrNykterstein' }),
      expect.anything(),
    );
  });
});
