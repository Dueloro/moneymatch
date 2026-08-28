import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { DemoSignInPage } from './DemoSignInPage';

const navigate = vi.fn();
const setGames = vi.fn();
const enterDemo = vi.fn().mockResolvedValue(undefined);

let meData: { user: { active_games: string[] } } | undefined = {
  user: {
    active_games: ['cs2.steam', 'pubg.steam', 'dota2.opendota', 'chess.lichess'],
  },
};

vi.mock('../auth/useAuth', () => ({ useAuth: () => ({ session: { user: {} } }) }));
vi.mock('../lib/demoAuth', () => ({ enterDemo: () => enterDemo() }));
vi.mock('../lib/toast', () => ({ toast: { error: vi.fn() } }));
vi.mock('../hooks/useMe', () => ({
  useMe: () => ({ data: meData }),
  useSetActiveGames: () => ({ mutate: setGames, isPending: false }),
}));
vi.mock('react-router-dom', async () => {
  const actual =
    await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigate };
});

function tile(name: RegExp) {
  return screen.getByRole('button', { name });
}

describe('DemoSignInPage — mounted overlay', () => {
  beforeEach(() => {
    navigate.mockClear();
    setGames.mockClear();
    enterDemo.mockClear();
    meData = {
      user: {
        active_games: ['cs2.steam', 'pubg.steam', 'dota2.opendota', 'chess.lichess'],
      },
    };
  });

  it('shows the game-select overlay in demo context once the session is ready', () => {
    renderWithProviders(<DemoSignInPage />);
    // Demo context: Dota 2 is selectable despite SOON, and starts selected from
    // the demo's pre-provisioned play set.
    const dota = tile(/^Dota 2,/);
    expect(dota).not.toBeDisabled();
    expect(dota).toHaveAttribute('aria-pressed', 'true');
  });

  it('enforces the minimum-one rule (Chess is a default, not a lock)', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DemoSignInPage />);
    // Turn off the three optional games; Chess remains as the default choice.
    for (const re of [/^Counter-Strike 2,/, /^PUBG,/, /^Dota 2,/]) {
      await user.click(tile(re));
      expect(tile(re)).toHaveAttribute('aria-pressed', 'false');
    }
    expect(tile(/^Chess,/)).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled();

    // Chess is now deselectable too — dropping it trips the minimum-one guard.
    await user.click(tile(/^Chess,/));
    expect(tile(/^Chess,/)).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Pick at least one game to continue.',
    );
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
  });

  it('confirming writes the chosen set and navigates to /play', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DemoSignInPage />);
    await user.click(tile(/^Dota 2,/)); // drop Dota
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    expect(setGames).toHaveBeenCalledTimes(1);
    const [picked, opts] = setGames.mock.calls[0];
    expect(picked).toContain('chess.lichess');
    expect(picked).not.toContain('dota2.opendota');
    // The write path matches C1's backfill shape (a list of catalog ids).
    (opts as { onSuccess: () => void }).onSuccess();
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith('/play', { replace: true }),
    );
  });

  it('shows the entering state before the session/profile are ready', () => {
    meData = undefined;
    renderWithProviders(<DemoSignInPage />);
    expect(screen.getByText('Entering demo…')).toBeInTheDocument();
  });
});
