import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { GettingStarted } from './GettingStarted';

const setDismissed = vi.fn();

let me: {
  user: { dismissed_checklists: string[] };
  getting_started: { linked_game: boolean; placed_wager: boolean; complete: boolean };
};

vi.mock('../hooks/useMe', () => ({
  useMe: () => ({ data: me }),
  useSetDismissedChecklists: () => ({ mutate: setDismissed }),
}));

describe('GettingStarted', () => {
  beforeEach(() => {
    setDismissed.mockClear();
    me = {
      user: { dismissed_checklists: [] },
      getting_started: { linked_game: false, placed_wager: false, complete: false },
    };
  });

  it('shows both steps for a new player', () => {
    renderWithProviders(<GettingStarted />);
    expect(screen.getByText('Get started', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('Link your Lichess account').tagName).toBe('A');
    expect(screen.getByText('Play your first match').tagName).toBe('A');
  });

  it('strikes through the link step once Lichess is linked', () => {
    me.getting_started.linked_game = true;
    renderWithProviders(<GettingStarted />);
    expect(screen.getByText('Link your Lichess account')).toHaveClass('line-through');
    expect(screen.getByText('Play your first match')).not.toHaveClass('line-through');
  });

  it('hides once complete', () => {
    me.getting_started = { linked_game: true, placed_wager: true, complete: true };
    const { container } = renderWithProviders(<GettingStarted />);
    expect(container).toBeEmptyDOMElement();
  });

  it('hides once dismissed (server-side, survives reload)', () => {
    me.user.dismissed_checklists = ['chess.lichess'];
    const { container } = renderWithProviders(<GettingStarted />);
    expect(container).toBeEmptyDOMElement();
  });

  it('dismiss X records chess as dismissed', async () => {
    const user = userEvent.setup();
    renderWithProviders(<GettingStarted />);
    await user.click(screen.getByRole('button', { name: 'Dismiss checklist' }));
    expect(setDismissed).toHaveBeenCalledWith('chess.lichess');
  });

  it('renders nothing before /me loads a user', () => {
    me = undefined as never;
    const { container } = renderWithProviders(<GettingStarted />);
    expect(container).toBeEmptyDOMElement();
  });
});
