import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { TournamentPage } from './TournamentPage';

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ isDemo: false, session: null }),
}));
vi.mock('../hooks/useWallet', () => ({
  useWallet: () => ({
    data: { available_cents: 100_000, escrow_cents: 0, lifetime_net_cents: 0 },
  }),
}));
vi.mock('../hooks/useGameSelection', () => ({
  useGameSelection: () => ({
    games: [{ game: 'cs2.steam', display_name: 'Counter Strike 2', status: 'LINKED' }],
    selected: 'cs2.steam',
    select: vi.fn(),
  }),
}));
vi.mock('../hooks/useTournaments', async () => ({
  // Keep the plain types/helpers; mock only the hooks.
  ...(await vi.importActual<typeof import('../hooks/useTournaments')>(
    '../hooks/useTournaments',
  )),
  useTournamentMarkets: vi.fn(),
  useTournamentStatus: vi.fn(),
  useEnterTournament: vi.fn(),
  useLeaveTournament: vi.fn(),
  useMyTournaments: vi.fn(),
}));

import {
  useEnterTournament,
  useLeaveTournament,
  useMyTournaments,
  useTournamentMarkets,
  useTournamentStatus,
} from '../hooks/useTournaments';

const enterMutate = vi.fn();

function mockStatus(s: unknown) {
  vi.mocked(useTournamentStatus).mockReturnValue({ data: s } as ReturnType<
    typeof useTournamentStatus
  >);
}

const TABLES = [
  { entry_cents: 500, players: 0 },
  { entry_cents: 1000, players: 3 },
  { entry_cents: 2500, players: 0 },
];
const KD_METRIC = {
  metric: 'cs2_kd_ratio',
  label: 'K/D ratio',
  provisional: false,
  rules: 'Your best K/D ratio from your first 3 matches after you join.',
  open_tables: TABLES,
};
const MARKETS = {
  game: 'cs2.steam',
  linked: true,
  entry_presets_cents: [500, 1000, 2500],
  prize_split: [60, 25, 15],
  field_size: 10,
  min_players: 2,
  score_matches: 3,
  join_window_seconds: 3600,
  duration_seconds: 10800,
  metrics: [KD_METRIC],
};
const ADR_METRIC = {
  ...KD_METRIC,
  metric: 'cs2_kills',
  label: 'ADR',
  rules: 'Your best kills.',
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
    vi.mocked(useMyTournaments).mockReturnValue({ data: [] } as unknown as ReturnType<
      typeof useMyTournaments
    >);
    vi.mocked(useLeaveTournament).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useLeaveTournament>);
  });

  it('renders one card per metric and joins with the entry chosen inside it', () => {
    renderWithProviders(<TournamentPage />);
    // 1 metric = 1 card, with its rules and the real player count at the
    // selected entry.
    expect(screen.getAllByRole('button', { name: 'Join tournament' })).toHaveLength(1);
    expect(screen.getByText('top 3 paid')).toBeInTheDocument();
    expect(screen.getByText(/best K\/D ratio from your first 3/)).toBeInTheDocument();
    expect(screen.getByText('3 of 10 in')).toBeInTheDocument();

    // Join the $10 card: a first tap arms, the confirm commits (the entry is
    // final once anyone else joins).
    const card = screen
      .getByRole('button', { name: 'Join tournament' })
      .closest('.rounded-card')!;
    fireEvent.click(
      within(card as HTMLElement).getByRole('button', { name: 'Join tournament' }),
    );
    expect(enterMutate).not.toHaveBeenCalled();
    fireEvent.click(
      within(card as HTMLElement).getByRole('button', { name: /Confirm/ }),
    );
    expect(enterMutate).toHaveBeenCalledWith({
      game: 'cs2.steam',
      metric: 'cs2_kd_ratio',
      entry_preset_cents: 1000,
    });
  });

  it('shows your tournament with standings and why each game counted', () => {
    mockStatus({
      status: 'formed',
      tournament: {
        id: 't1',
        game: 'cs2.steam',
        metric: 'cs2_kd_ratio',
        metric_label: 'K/D ratio',
        entry_cents: 1000,
        pot_cents: 10000,
        prize_cents: 0,
        rake_cents: 0,
        prize_split: [60, 25, 15],
        field_size: 10,
        players: 4,
        score_matches: 3,
        state: 'LOCKED',
        window_starts_at: new Date().toISOString(),
        window_ends_at: new Date().toISOString(),
        join_closes_at: new Date().toISOString(),
        your_entered_at: new Date().toISOString(),
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
        your_games: [
          {
            host_match_id: 'g1',
            started_at: new Date().toISOString(),
            ended_at: null,
            mode: 'premier',
            result: 'win',
            reason: 'COUNTED',
            reason_text: 'Counted',
            value: 1.6,
          },
          {
            host_match_id: 'g0',
            started_at: new Date().toISOString(),
            ended_at: null,
            mode: 'premier',
            result: 'loss',
            reason: 'STARTED_BEFORE_ENTRY',
            reason_text: 'Started before you joined',
            value: null,
          },
        ],
        outcome_reason: null,
        resolved_at: null,
      },
    });
    renderWithProviders(<TournamentPage />);
    expect(screen.getByTestId('standings-panel')).toBeInTheDocument();
    expect(screen.getByText(/#1 you/)).toBeInTheDocument();
    expect(screen.getByText(/4 of 10 players · pot \$100.00/)).toBeInTheDocument();
    const games = screen.getByTestId('your-games');
    expect(within(games).getByText('Counted')).toBeInTheDocument();
    expect(within(games).getByText('Started before you joined')).toBeInTheDocument();
    // Already in one: the cards can't start a second.
    expect(
      screen.getAllByRole('button', { name: "You're in a tournament" })[0],
    ).toBeDisabled();
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
      data: { ...MARKETS, metrics: [KD_METRIC, ADR_METRIC] },
    } as unknown as ReturnType<typeof useTournamentMarkets>);
    renderWithProviders(<TournamentPage />);
    // Baseline: 2 metrics × 3 presets = 6 cards.
    expect(screen.getAllByRole('button', { name: 'Join tournament' })).toHaveLength(2);
    fireEvent.click(screen.getByTestId('tournament-filters-toggle'));
    const filters = screen.getByTestId('tournament-filters');
    fireEvent.click(within(filters).getByRole('button', { name: 'ADR' }));
    expect(screen.getAllByRole('button', { name: 'Join tournament' })).toHaveLength(1);
  });

  it('takes a finished tournament off the page (its record is kept server-side)', () => {
    vi.mocked(useMyTournaments).mockReturnValue({
      data: [
        {
          id: 't9',
          game: 'pubg.steam',
          metric: 'pubg_kills',
          metric_label: 'Kills',
          entry_cents: 1000,
          pot_cents: 1000,
          prize_cents: 0,
          rake_cents: 0,
          prize_split: [60, 25, 15],
          field_size: 10,
          players: 1,
          score_matches: 3,
          state: 'CANCELED',
          window_starts_at: new Date().toISOString(),
          window_ends_at: new Date().toISOString(),
          join_closes_at: new Date().toISOString(),
          your_entered_at: new Date().toISOString(),
          field_mu_low: null,
          field_mu_high: null,
          standings: [],
          your_rank: null,
          your_payout_cents: 1000,
          your_games: [],
          outcome_reason: 'not_enough_players',
          resolved_at: new Date().toISOString(),
        },
      ],
    } as unknown as ReturnType<typeof useMyTournaments>);
    renderWithProviders(<TournamentPage />);
    expect(screen.queryByTestId('standings-panel')).not.toBeInTheDocument();
  });
});
