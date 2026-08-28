import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { GameChecklists } from './GameChecklists';

const setDismissed = vi.fn();

let me: {
  user: { active_games: string[]; dismissed_checklists: string[] };
  contested_games: string[];
};
let links: { games: { game: string; status: string }[] };

vi.mock('../hooks/useMe', () => ({
  useMe: () => ({ data: me }),
  useSetDismissedChecklists: () => ({ mutate: setDismissed }),
}));
vi.mock('../hooks/useLinks', () => ({
  useLinks: () => ({ data: links }),
}));

describe('GameChecklists — per-game Play-tab onboarding', () => {
  beforeEach(() => {
    setDismissed.mockClear();
    me = {
      user: {
        active_games: ['chess.lichess', 'cs2.steam'],
        dismissed_checklists: [],
      },
      contested_games: [],
    };
    links = { games: [] };
  });

  it('shows one card per active game that is not dismissed', () => {
    renderWithProviders(<GameChecklists />);
    expect(
      screen.getByText('Get started with Chess', { exact: false }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Get started with Counter-Strike 2', { exact: false }),
    ).toBeInTheDocument();
  });

  it('hides a game whose checklist was dismissed (server-side → survives reload)', () => {
    me.user.dismissed_checklists = ['cs2.steam'];
    renderWithProviders(<GameChecklists />);
    expect(
      screen.getByText('Get started with Chess', { exact: false }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Get started with Counter-Strike 2', { exact: false }),
    ).not.toBeInTheDocument();
  });

  it('dismiss X mutates the clicked game (hook computes the full list)', async () => {
    const user = userEvent.setup();
    renderWithProviders(<GameChecklists />);
    await user.click(
      screen.getByRole('button', { name: 'Dismiss Counter-Strike 2 checklist' }),
    );
    expect(setDismissed).toHaveBeenCalledWith('cs2.steam');
  });

  it('marks the link step done for a linked game', () => {
    links = { games: [{ game: 'cs2.steam', status: 'LINKED' }] };
    renderWithProviders(<GameChecklists />);
    const linkStep = screen.getByText('Link your Counter-Strike 2 account');
    expect(linkStep).toHaveClass('line-through');
  });

  it('hides a fully-complete game (linked + has entered a contest)', () => {
    me.user.active_games = ['cs2.steam'];
    me.contested_games = ['cs2.steam'];
    links = { games: [{ game: 'cs2.steam', status: 'LINKED' }] };
    renderWithProviders(<GameChecklists />);
    expect(
      screen.queryByText('Get started with Counter-Strike 2', { exact: false }),
    ).not.toBeInTheDocument();
  });

  it('checks "join your first contest" per game — only for games actually entered', () => {
    // Active on two games, but only chess has a contest entered.
    me.user.active_games = ['chess.lichess', 'cs2.steam'];
    me.contested_games = ['chess.lichess'];
    renderWithProviders(<GameChecklists />);
    // Chess: contest step done (struck through).
    expect(screen.getByText('Join your first Chess contest')).toHaveClass(
      'line-through',
    );
    // CS2: contest step still open — a link, not struck through.
    const cs2Step = screen.getByText('Join your first Counter-Strike 2 contest');
    expect(cs2Step).not.toHaveClass('line-through');
    expect(cs2Step.tagName).toBe('A');
  });

  it('renders nothing before /me loads a user', () => {
    me = undefined as never;
    const { container } = renderWithProviders(<GameChecklists />);
    expect(container).toBeEmptyDOMElement();
  });
});
