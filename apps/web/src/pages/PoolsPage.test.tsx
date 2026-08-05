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

  it('renders one card per bar, with entry as a control inside it', () => {
    renderWithProviders(<PoolsPage />);
    // 3 difficulties = 3 cards. Entry is a segmented control inside each card
    // rather than a third grid dimension, so no sentence repeats.
    expect(screen.getAllByRole('button', { name: 'Join pool' })).toHaveLength(3);
    expect(screen.getByText('Clear 1.8')).toBeInTheDocument();
    // The clear rate is a meter carrying the real number, not a sentence.
    expect(screen.getByText('16%')).toBeInTheDocument();
    // Payout for the default (middle) entry on the medium bar: $10 -> $56.25.
    expect(screen.getByText('$56.25')).toBeInTheDocument();
  });

  it('joining a pool uses the entry selected inside that card', () => {
    renderWithProviders(<PoolsPage />);
    const card = screen.getByText('Clear 1.8').closest('.rounded-card')!;
    // Defaults to the middle preset ($10).
    fireEvent.click(
      within(card as HTMLElement).getByRole('button', { name: 'Join pool' }),
    );
    expect(enterMutate).toHaveBeenCalledWith({
      game: 'cs2.faceit',
      metric: 'cs2_kd_ratio',
      difficulty: 'medium',
      entry_preset_cents: 1000,
    });

    // Changing the entry inside the card changes what gets joined.
    fireEvent.click(within(card as HTMLElement).getByRole('tab', { name: '$25.00' }));
    fireEvent.click(
      within(card as HTMLElement).getByRole('button', { name: 'Join pool' }),
    );
    expect(enterMutate).toHaveBeenLastCalledWith({
      game: 'cs2.faceit',
      metric: 'cs2_kd_ratio',
      difficulty: 'medium',
      entry_preset_cents: 2500,
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
    expect(screen.getAllByRole('button', { name: 'Join pool' })).toHaveLength(3);
    fireEvent.click(screen.getByTestId('pool-filters-toggle'));
    const filters = screen.getByTestId('pool-filters');
    fireEvent.click(within(filters).getByRole('button', { name: 'hard' }));
    expect(screen.getAllByRole('button', { name: 'Join pool' })).toHaveLength(1);
  });
});
