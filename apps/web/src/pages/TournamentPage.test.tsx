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

const MARKETS = {
  game: 'cs2.faceit',
  linked: true,
  entry_presets_cents: [500, 1000, 2500],
  prize_split: [50, 30, 20],
  field_size: 10,
  score_matches: 3,
  metrics: [{ metric: 'cs2_kd_ratio', label: 'K/D ratio', provisional: false }],
};
const ADR_METRIC = { metric: 'cs2_adr', label: 'ADR', provisional: false };

describe('TournamentPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useTournamentMarkets).mockReturnValue({
      data: MARKETS,
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

  it('renders one card per metric and joins with the entry chosen inside it', () => {
    renderWithProviders(<TournamentPage />);
    // 1 metric = 1 card. The advertised field size is the server's, not a
    // number invented per entry preset.
    expect(screen.getAllByRole('button', { name: 'Join tournament' })).toHaveLength(1);
    expect(screen.getByText('top 3 paid')).toBeInTheDocument();

    // Join the $10 card (its entry amount is unique across cards).
    const card = screen
      .getByRole('button', { name: 'Join tournament' })
      .closest('.rounded-card')!;
    fireEvent.click(
      within(card as HTMLElement).getByRole('button', { name: 'Join tournament' }),
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

  it('the filter menu is collapsed until the hamburger toggle is clicked', () => {
    // A single metric hides the filter bar entirely, so use two here.
    vi.mocked(useTournamentMarkets).mockReturnValue({
      data: { ...MARKETS, metrics: [...MARKETS.metrics, ADR_METRIC] },
    } as unknown as ReturnType<typeof useTournamentMarkets>);
    renderWithProviders(<TournamentPage />);
    expect(screen.queryByTestId('tournament-filters')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('tournament-filters-toggle'));
    expect(screen.getByTestId('tournament-filters')).toBeInTheDocument();
  });

  it('metric filter trims the grid to the chosen metric', () => {
    // Two open metrics so the Metric chip row appears (hidden for a single one).
    vi.mocked(useTournamentMarkets).mockReturnValue({
      data: {
        game: 'cs2.faceit',
        linked: true,
        entry_presets_cents: [500, 1000, 2500],
        prize_split: [50, 30, 20],
        field_size: 10,
        score_matches: 3,
        metrics: [
          { metric: 'cs2_kd_ratio', label: 'K/D ratio', provisional: false },
          { metric: 'cs2_adr', label: 'ADR', provisional: false },
        ],
      },
    } as unknown as ReturnType<typeof useTournamentMarkets>);
    renderWithProviders(<TournamentPage />);
    // Baseline: 2 metrics × 3 presets = 6 cards.
    expect(screen.getAllByRole('button', { name: 'Join tournament' })).toHaveLength(2);
    fireEvent.click(screen.getByTestId('tournament-filters-toggle'));
    const filters = screen.getByTestId('tournament-filters');
    fireEvent.click(within(filters).getByRole('button', { name: 'ADR' }));
    expect(screen.getAllByRole('button', { name: 'Join tournament' })).toHaveLength(1);
  });
});
