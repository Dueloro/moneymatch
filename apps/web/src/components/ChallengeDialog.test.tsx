import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { ChallengeDialog } from './ChallengeDialog';

const mutateAsync = vi.fn();
vi.mock('../hooks/useChallenges', () => ({
  useCreateChallenge: () => ({ mutateAsync, isPending: false, error: null }),
}));
vi.mock('../hooks/useMatchmaking', async () => {
  const actual = await vi.importActual<typeof import('../hooks/useMatchmaking')>(
    '../hooks/useMatchmaking',
  );
  return {
    ...actual,
    useMarkets: () => ({
      data: {
        game: 'chess',
        linked: true,
        entry_presets_cents: [1000, 2500, 5000],
        markets: [
          {
            key: 'win_h2h',
            label: 'Head to head',
            kind: 'win_h2h',
            requires_speed: true,
            speeds: ['bullet', 'blitz', 'rapid'],
            multiplier_bps: 18000,
            queue_depth: 0,
            resolution_note: '',
          },
        ],
      },
    }),
  };
});

function open(onClose = vi.fn()) {
  renderWithProviders(
    <ChallengeDialog friend={{ user_id: 'u2', username: 'bob' }} onClose={onClose} />,
  );
}

describe('ChallengeDialog', () => {
  beforeEach(() => mutateAsync.mockReset());

  it('defaults to blitz and the middle stake, so the action is enabled', () => {
    open();
    expect(screen.getByRole('tab', { name: /Blitz/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('tab', { name: '2,500 pts' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(
      screen.getByRole('button', { name: /Challenge bob · 2,500 pts/ }),
    ).toBeEnabled();
  });

  it('shows the payout and fee for the chosen stake', async () => {
    open();
    expect(screen.getByTestId('desk-prize')).toHaveTextContent('4,500 pts');
    expect(screen.getByText(/a draw refunds both/)).toHaveTextContent('Fee 500 pts');
    await userEvent.click(screen.getByRole('tab', { name: '5,000 pts' }));
    expect(screen.getByTestId('desk-prize')).toHaveTextContent('9,000 pts');
  });

  it('sends the defaults to the friend', async () => {
    const onClose = vi.fn();
    open(onClose);
    await userEvent.click(screen.getByRole('button', { name: /Challenge bob/ }));
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        challengee_id: 'u2',
        speed: 'blitz',
        entry_preset_cents: 2500,
      }),
    );
    expect(onClose).toHaveBeenCalled();
  });

  it('closes on Escape', async () => {
    const onClose = vi.fn();
    open(onClose);
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });

  it('copies the invite link and shows Copied', async () => {
    const user = userEvent.setup();
    mutateAsync.mockResolvedValue({ invite_path: '/invite/abc' });
    open();
    await user.click(screen.getByRole('button', { name: 'Copy invite link' }));
    expect(await navigator.clipboard.readText()).toBe(
      `${window.location.origin}/invite/abc`,
    );
    expect(screen.getAllByText('Copied').length).toBeGreaterThan(0);
  });
});
