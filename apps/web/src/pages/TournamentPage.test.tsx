import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { pts, renderWithProviders } from '../test/testUtils';
import { TournamentPage } from './TournamentPage';

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ session: null }),
}));
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

const MARKETS = {
  game: 'chess.lichess',
  linked: true,
  entry_presets_cents: [500, 1000, 2500],
  prize_split: [50, 30, 20],
  field_size: 10,
  metrics: [{ metric: 'chess_wins', label: 'Total wins', provisional: false }],
};
const STREAK_METRIC = {
  metric: 'chess_win_streak',
  label: 'Longest win streak',
  provisional: false,
};

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
    expect(screen.getAllByRole('button', { name: 'Join tournament' })).toHaveLength(1);
    expect(screen.getByText('10 players · top 3 paid')).toBeInTheDocument();
    // 10 x 1,000 pot, minus the 10% fee, times the 50/100 first-place share.
    expect(screen.getByText('1st place if full')).toBeInTheDocument();
    expect(screen.getByText(pts('4,500 pts'))).toBeInTheDocument();
    expect(
      screen.getByText('Most wins across your games in the window ranks first.'),
    ).toBeInTheDocument();

    const card = screen
      .getByRole('button', { name: 'Join tournament' })
      .closest('.rounded-card')!;
    fireEvent.click(
      within(card as HTMLElement).getByRole('button', { name: 'Join tournament' }),
    );
    expect(enterMutate).toHaveBeenCalledWith({
      game: 'chess.lichess',
      metric: 'chess_wins',
      entry_preset_cents: 1000,
    });
  });

  it('shows live standings when a field is formed', () => {
    mockStatus({
      status: 'formed',
      tournament: {
        id: 't1',
        game: 'chess.lichess',
        metric: 'chess_wins',
        metric_label: 'Total wins',
        entry_cents: 1000,
        pot_cents: 10000,
        prize_cents: 0,
        rake_cents: 0,
        prize_split: [50, 30, 20],
        field_size: 10,
        state: 'LOCKED',
        window_starts_at: new Date().toISOString(),
        window_ends_at: new Date(Date.now() + 2 * 3600e3 + 14.5 * 60e3).toISOString(),
        field_mu_low: 1500,
        field_mu_high: 1600,
        standings: [
          {
            user_id: 'u1',
            username: 'you',
            score: 3,
            matches: 5,
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
    expect(screen.getByText('3 wins · 5 games')).toBeInTheDocument();
    expect(
      screen.getAllByText('Most wins across your games in the window ranks first.')
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getByText('Pot 10,000 pts · closes in 2h 14m')).toBeInTheDocument();
  });

  it('the filter menu is collapsed until the hamburger toggle is clicked', () => {
    vi.mocked(useTournamentMarkets).mockReturnValue({
      data: { ...MARKETS, metrics: [...MARKETS.metrics, STREAK_METRIC] },
    } as unknown as ReturnType<typeof useTournamentMarkets>);
    renderWithProviders(<TournamentPage />);
    expect(screen.queryByTestId('tournament-filters')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('tournament-filters-toggle'));
    expect(screen.getByTestId('tournament-filters')).toBeInTheDocument();
  });

  it('metric filter trims the grid to the chosen metric', () => {
    vi.mocked(useTournamentMarkets).mockReturnValue({
      data: {
        game: 'chess.lichess',
        linked: true,
        entry_presets_cents: [500, 1000, 2500],
        prize_split: [50, 30, 20],
        field_size: 10,
        metrics: [
          { metric: 'chess_wins', label: 'Total wins', provisional: false },
          {
            metric: 'chess_win_streak',
            label: 'Longest win streak',
            provisional: false,
          },
        ],
      },
    } as unknown as ReturnType<typeof useTournamentMarkets>);
    renderWithProviders(<TournamentPage />);
    expect(screen.getAllByRole('button', { name: 'Join tournament' })).toHaveLength(2);
    fireEvent.click(screen.getByTestId('tournament-filters-toggle'));
    const filters = screen.getByTestId('tournament-filters');
    fireEvent.click(
      within(filters).getByRole('button', { name: 'Longest win streak' }),
    );
    expect(screen.getAllByRole('button', { name: 'Join tournament' })).toHaveLength(1);
  });
});
