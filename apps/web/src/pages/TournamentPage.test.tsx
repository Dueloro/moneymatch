import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { TournamentPage } from './TournamentPage';

vi.mock('../hooks/useWallet', () => ({
  useWallet: () => ({
    data: { available_cents: 100_000, escrow_cents: 0, lifetime_net_cents: 0 },
  }),
}));
vi.mock('../hooks/useTournaments', () => ({
  useTournamentMarkets: vi.fn(),
  useTournamentStatus: vi.fn(),
  useEnterTournament: vi.fn(),
  useLeaveTournament: vi.fn(),
}));

import {
  useEnterTournament,
  useLeaveTournament,
  useTournamentMarkets,
  useTournamentStatus,
} from '../hooks/useTournaments';

const enterMutate = vi.fn();

function mockStatus(s: unknown) {
  vi.mocked(useTournamentStatus).mockReturnValue({ data: s } as ReturnType<
    typeof useTournamentStatus
  >);
}

describe('TournamentPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useTournamentMarkets).mockReturnValue({
      data: {
        game: 'cs2.faceit',
        linked: true,
        entry_presets_cents: [500, 1000, 2500],
        prize_split: [50, 30, 20],
        field_size: 10,
        score_matches: 3,
        metrics: [{ metric: 'cs2_kd_ratio', label: 'K/D ratio', provisional: false }],
      },
    } as unknown as ReturnType<typeof useTournamentMarkets>);
    mockStatus({ status: 'idle', tournament: null });
    vi.mocked(useEnterTournament).mockReturnValue({
      mutate: enterMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useEnterTournament>);
    vi.mocked(useLeaveTournament).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useLeaveTournament>);
  });

  it('shows the 50/30/20 field format and enters on a preset', () => {
    renderWithProviders(<TournamentPage />);
    expect(screen.getByText(/top 3 split 50\/30\/20/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '$10.00' }));
    fireEvent.click(screen.getByRole('button', { name: 'Enter' }));
    expect(enterMutate).toHaveBeenCalledWith({
      game: 'cs2.faceit',
      metric: 'cs2_kd_ratio',
      entry_preset_cents: 1000,
    });
  });

  it('renders the field μ-spread and live standings when formed', () => {
    mockStatus({
      status: 'formed',
      tournament: {
        id: 't1',
        game: 'cs2.faceit',
        metric: 'cs2_kd_ratio',
        metric_label: 'K/D ratio',
        entry_cents: 1000,
        pot_cents: 10000,
        prize_cents: 0,
        rake_cents: 0,
        prize_split: [50, 30, 20],
        field_size: 10,
        score_matches: 3,
        state: 'LOCKED',
        window_starts_at: new Date().toISOString(),
        window_ends_at: new Date().toISOString(),
        field_mu_low: 1.42,
        field_mu_high: 1.58,
        standings: [
          {
            user_id: 'u1',
            username: 'you',
            score: 1.6,
            matches: 2,
            rank: 1,
            is_you: true,
            payout_cents: 0,
          },
        ],
        your_rank: 1,
        your_payout_cents: null,
        resolved_at: null,
      },
    });
    renderWithProviders(<TournamentPage />);
    expect(screen.getByTestId('standings-panel')).toBeInTheDocument();
    expect(screen.getByText(/Field: K\/D ratio 1.42–1.58/)).toBeInTheDocument();
    expect(screen.getByText(/#1 you/)).toBeInTheDocument();
  });
});
