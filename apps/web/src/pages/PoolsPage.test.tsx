import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { PoolsPage } from './PoolsPage';

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ isDemo: false, session: null }),
}));
vi.mock('../hooks/useWallet', () => ({
  useWallet: () => ({
    data: { available_cents: 100_000, escrow_cents: 0, lifetime_net_cents: 0 },
  }),
}));
// GettingStarted (rendered by PoolsPage) reads /me; null = checklist hidden.
vi.mock('../hooks/useMe', () => ({
  useMe: () => ({ data: { getting_started: null } }),
}));
vi.mock('../hooks/useGameSelection', () => ({
  useGameSelection: () => ({
    games: [{ game: 'cs2.faceit', display_name: 'Counter Strike 2', status: 'LINKED' }],
    selected: 'cs2.faceit',
    select: vi.fn(),
  }),
}));
vi.mock('../hooks/usePools', async () => {
  const actual =
    await vi.importActual<typeof import('../hooks/usePools')>('../hooks/usePools');
  return {
    ...actual,
    usePoolMarkets: vi.fn(),
    usePoolStatus: vi.fn(),
    useEnterPool: vi.fn(),
    useLeavePool: vi.fn(),
    estPrize: actual.estPrize,
  };
});

import {
  useEnterPool,
  useLeavePool,
  usePoolMarkets,
  usePoolStatus,
} from '../hooks/usePools';

const enterMutate = vi.fn();

const KD_METRIC = {
  metric: 'cs2_kd_ratio',
  label: 'K/D ratio',
  provisional: false,
  cards: [
    { difficulty: 'easy', bar: 1.65, clear_rate: 0.31, est_multiplier_bps: 29000 },
    { difficulty: 'medium', bar: 1.8, clear_rate: 0.16, est_multiplier_bps: 56250 },
    { difficulty: 'hard', bar: 2.0, clear_rate: 0.04, est_multiplier_bps: 225000 },
  ],
};

function mockStatus(s: unknown) {
  vi.mocked(usePoolStatus).mockReturnValue({ data: s } as ReturnType<
    typeof usePoolStatus
  >);
}

describe('PoolsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(usePoolMarkets).mockReturnValue({
      data: {
        game: 'cs2.faceit',
        linked: true,
        entry_presets_cents: [500, 1000, 2500],
        metrics: [KD_METRIC],
      },
    } as unknown as ReturnType<typeof usePoolMarkets>);
    mockStatus({ status: 'idle', pool: null });
    vi.mocked(useEnterPool).mockReturnValue({
      mutate: enterMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useEnterPool>);
    vi.mocked(useLeavePool).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useLeavePool>);
  });

  it('renders a joinable card per difficulty × entry with bar + estimated payout', () => {
    renderWithProviders(<PoolsPage />);
    // 3 difficulties × 3 entry presets = 9 cards, each with a Join Pool button.
    expect(screen.getAllByRole('button', { name: 'Join Pool' })).toHaveLength(9);
    // The medium-bar cards show the bar and disclosed clear rate.
    expect(screen.getAllByText('K/D ratio ≥ 1.8').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Clears ≈ 16%/).length).toBeGreaterThan(0);
    // Estimated payout is disclosed per card (medium @ $10 → $56.25).
    expect(screen.getByText('Est. payout ≈ $56.25')).toBeInTheDocument();
  });

  it('joining a pool card enters the queue with its preset params', () => {
    renderWithProviders(<PoolsPage />);
    // medium @ $10 is the only card with this exact estimated payout.
    const card = screen.getByText('Est. payout ≈ $56.25').closest('.rounded-2xl')!;
    fireEvent.click(
      within(card as HTMLElement).getByRole('button', { name: 'Join Pool' }),
    );
    expect(enterMutate).toHaveBeenCalledWith({
      game: 'cs2.faceit',
      metric: 'cs2_kd_ratio',
      difficulty: 'medium',
      entry_preset_cents: 1000,
    });
  });

  it('shows the formed room banner with the room bar', () => {
    mockStatus({
      status: 'formed',
      pool: {
        id: 'p1',
        game: 'cs2.faceit',
        metric: 'cs2_kd_ratio',
        metric_label: 'K/D ratio',
        difficulty: 'medium',
        room_bar: 1.75,
        your_bar: 1.8,
        bar_delta: -0.05,
        entry_cents: 1000,
        pot_cents: 4000,
        prize_cents: 0,
        rake_cents: 0,
        room_size: 4,
        state: 'LOCKED',
        window_starts_at: new Date().toISOString(),
        window_ends_at: new Date().toISOString(),
        members: [],
        your_payout_cents: null,
        resolved_at: null,
      },
    });
    renderWithProviders(<PoolsPage />);
    expect(screen.getByTestId('room-card')).toBeInTheDocument();
    expect(screen.getByText(/bar 1.75/)).toBeInTheDocument(); // room bar
    expect(screen.getByText(/4 players · pot \$40.00/)).toBeInTheDocument();
    // The "you can now play" cue reassures the entry is escrowed.
    expect(screen.getByTestId('room-play-cue')).toHaveTextContent(
      /you can now play your .* game/i,
    );
  });

  it('the filter menu is collapsed until the hamburger toggle is clicked', () => {
    renderWithProviders(<PoolsPage />);
    // Tucked away by default — only the toggle shows, not the panel.
    expect(screen.queryByTestId('pool-filters')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('pool-filters-toggle'));
    expect(screen.getByTestId('pool-filters')).toBeInTheDocument();
  });

  it('difficulty filter trims the grid to the chosen difficulty', () => {
    renderWithProviders(<PoolsPage />);
    // Baseline: 3 difficulties × 3 presets = 9 cards.
    expect(screen.getAllByRole('button', { name: 'Join Pool' })).toHaveLength(9);
    fireEvent.click(screen.getByTestId('pool-filters-toggle'));
    const filters = screen.getByTestId('pool-filters');
    fireEvent.click(within(filters).getByRole('button', { name: 'hard' }));
    // Only the hard difficulty × 3 presets remain.
    expect(screen.getAllByRole('button', { name: 'Join Pool' })).toHaveLength(3);
  });

  it('entry filter trims the grid to the chosen entry amount', () => {
    renderWithProviders(<PoolsPage />);
    fireEvent.click(screen.getByTestId('pool-filters-toggle'));
    const filters = screen.getByTestId('pool-filters');
    fireEvent.click(within(filters).getByRole('button', { name: '$25.00' }));
    // 3 difficulties × 1 entry preset = 3 cards.
    expect(screen.getAllByRole('button', { name: 'Join Pool' })).toHaveLength(3);
  });
});
