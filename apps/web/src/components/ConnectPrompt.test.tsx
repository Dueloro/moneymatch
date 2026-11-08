import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { ConnectPrompt } from './ConnectPrompt';

const dismiss = vi.fn();
let dismissed: string[] = [];
let games: { status: string }[] = [];

vi.mock('../hooks/useMe', () => ({
  useMe: () => ({ data: { user: { dismissed_checklists: dismissed } } }),
  useSetDismissedChecklists: () => ({ mutate: dismiss }),
}));
vi.mock('../hooks/useLinks', () => ({
  useLinks: () => ({ data: { games } }),
  useConnectLichess: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}));

describe('ConnectPrompt', () => {
  beforeEach(() => {
    dismiss.mockClear();
    dismissed = [];
    games = [{ status: 'UNLINKED' }];
  });

  it('asks an unlinked player to connect Lichess', () => {
    renderWithProviders(<ConnectPrompt />, { route: '/activity' });
    expect(screen.getByText('Connect Lichess to play.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Connect Lichess' })).toBeInTheDocument();
  });

  it('stays out of the way on pages that already offer Connect', () => {
    for (const route of ['/play', '/pools', '/tournament', '/profile']) {
      const { unmount } = renderWithProviders(<ConnectPrompt />, { route });
      expect(screen.queryByTestId('connect-prompt')).not.toBeInTheDocument();
      unmount();
    }
  });

  it('disappears once linked', () => {
    games = [{ status: 'LINKED' }];
    renderWithProviders(<ConnectPrompt />, { route: '/activity' });
    expect(screen.queryByTestId('connect-prompt')).not.toBeInTheDocument();
  });

  it('dismisses for good via dismissed_checklists', async () => {
    renderWithProviders(<ConnectPrompt />, { route: '/wallet' });
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(dismiss).toHaveBeenCalledWith('chess.lichess');
  });

  it('stays hidden after a dismissal', () => {
    dismissed = ['chess.lichess'];
    renderWithProviders(<ConnectPrompt />, { route: '/social' });
    expect(screen.queryByTestId('connect-prompt')).not.toBeInTheDocument();
  });
});
