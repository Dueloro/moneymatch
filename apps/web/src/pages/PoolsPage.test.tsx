import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { PoolsPage } from './PoolsPage';

vi.mock('../hooks/useWallet', () => ({
  useWallet: () => ({
    data: { available_cents: 100_000, escrow_cents: 0, lifetime_net_cents: 0 },
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

  it('quotes difficulty bars from the viewer baseline with a disclosed estimate', () => {
    renderWithProviders(<PoolsPage />);
    expect(screen.getByText('1.8')).toBeInTheDocument(); // medium bar
    expect(screen.getByText('clears ≈ 16%')).toBeInTheDocument();
    // Estimated multiplier is disclosed as an estimate (≈), not a fixed line.
    expect(screen.getByText('≈ ×5.63')).toBeInTheDocument();
  });

  it('pick difficulty + entry shows the estimated share-of-pool copy and enters', () => {
    renderWithProviders(<PoolsPage />);
    fireEvent.click(screen.getByText('medium'));
    fireEvent.click(screen.getByRole('button', { name: '$10.00' }));
    expect(
      screen.getByText(/actual payout is your share of the pool/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Enter pool' }));
    expect(enterMutate).toHaveBeenCalledWith({
      game: 'cs2.faceit',
      metric: 'cs2_kd_ratio',
      difficulty: 'medium',
      entry_preset_cents: 1000,
    });
  });

  it('shows the formed room card with the room bar and delta', () => {
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
    expect(screen.getByText('1.75')).toBeInTheDocument(); // room bar
    expect(screen.getByText(/Your bar was 1.8/)).toBeInTheDocument();
  });
});
