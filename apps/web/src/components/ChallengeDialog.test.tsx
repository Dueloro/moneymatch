import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { ChallengeDialog } from './ChallengeDialog';

vi.mock('../hooks/useChallenges', () => ({
  useCreateChallenge: () => ({ mutateAsync: vi.fn(), isPending: false, error: null }),
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
        entry_presets_cents: [1000, 2500],
        markets: [
          {
            key: 'win_h2h',
            label: 'Head to head',
            kind: 'win_h2h',
            requires_speed: false,
            speeds: [],
            multiplier_bps: 18000,
            queue_depth: 0,
            resolution_note: '',
          },
        ],
      },
    }),
  };
});

describe('ChallengeDialog', () => {
  it('shows the fee in points for the chosen stake', () => {
    renderWithProviders(
      <ChallengeDialog friend={{ user_id: 'u2', username: 'bob' }} onClose={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '2,500 pts' }));
    expect(
      screen.getByText('Both stake 2,500 pts · winner takes 4,500 pts · fee 500 pts'),
    ).toBeInTheDocument();
  });
});
