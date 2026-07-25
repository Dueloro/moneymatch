import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { TournamentPage } from './TournamentPage';

vi.mock('../hooks/useWallet', () => ({
  useWallet: () => ({
    data: { available_cents: 100_000, escrow_cents: 0, lifetime_net_cents: 0 },
  }),
}));
vi.mock('../hooks/useGameSelection', () => ({
  useGameSelection: () => ({
    games: [{ game: 'cs2.faceit', display_name: 'Counter Strike 2', status: 'LINKED' }],
    selected: 'cs2.faceit',
    select: vi.fn(),
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

  it('renders joinable tournament cards (10-20 players) and joins with the preset', () => {
    renderWithProviders(<TournamentPage />);
    // 1 metric × 3 entry presets = 3 cards at advertised sizes 10 / 16 / 20.
    expect(screen.getAllByRole('button', { name: 'Join Tournament' })).toHaveLength(3);
    expect(screen.getByText('10 players')).toBeInTheDocument();
    expect(screen.getByText('16 players')).toBeInTheDocument();
    expect(screen.getByText('20 players')).toBeInTheDocument();
    expect(screen.getAllByText('Best 3 matches · top 3 split the pot').length).toBe(3);

    // Join the $10 card (its entry amount is unique across cards).
    const card = screen.getByText('$10.00').closest('.rounded-2xl')!;
    fireEvent.click(
      within(card as HTMLElement).getByRole('button', { name: 'Join Tournament' }),
    );
    expect(enterMutate).toHaveBeenCalledWith({
      game: 'cs2.faceit',
      metric: 'cs2_kd_ratio',
      entry_preset_cents: 1000,
    });
  });

  it('shows live standings when a field is formed', () => {
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
    expect(screen.getByText(/#1 you/)).toBeInTheDocument();
    expect(screen.getByText(/Pot \$100.00/)).toBeInTheDocument();
  });
});
