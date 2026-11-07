import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { PoolsPage } from './PoolsPage';

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ session: null }),
}));
vi.mock('../hooks/useWallet', () => ({
  useWallet: () => ({
    data: { available_cents: 100_000, escrow_cents: 0, lifetime_net_cents: 0 },
  }),
}));
// GettingStarted (rendered by PoolsPage) reads /me; no `user` → no checklist.
vi.mock('../hooks/useMe', () => ({
  useMe: () => ({ data: { getting_started: null } }),
  useSetDismissedChecklists: () => ({ mutate: vi.fn() }),
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

const MOVES_METRIC = {
  metric: 'chess_moves',
  label: 'Moves to win',
  provisional: false,
  cards: [
    { difficulty: 'easy', bar: 34, clear_rate: 0.35, est_multiplier_bps: 25700 },
    { difficulty: 'medium', bar: 28, clear_rate: 0.2, est_multiplier_bps: 36000 },
    // Capped at room_size x (1 - rake). Before that cap this card advertised
    // $225,000 on a $25 entry, which no pot could ever fund.
    { difficulty: 'hard', bar: 22, clear_rate: 0.1, est_multiplier_bps: 36000 },
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
        game: 'chess.lichess',
        linked: true,
        entry_presets_cents: [500, 1000, 2500],
        metrics: [MOVES_METRIC],
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
    expect(screen.getAllByText('Moves to win').length).toBeGreaterThan(0);
    expect(screen.getByText('28')).toBeInTheDocument(); // headline bar
    expect(screen.getByText('Win in 28 moves or fewer')).toBeInTheDocument();
    expect(
      screen.getAllByText('Wins only. A loss or a draw does not count.'),
    ).toHaveLength(3);
    // The clear rate is a meter carrying the real number, not a sentence.
    expect(screen.getByText('20%')).toBeInTheDocument();
    // Payout for the default (middle) entry on the medium bar: $10 -> $36.00.
    expect(screen.getAllByText('$36.00').length).toBeGreaterThan(0);
  });

  it('confirms in the card before joining, using the selected entry', () => {
    renderWithProviders(<PoolsPage />);
    const card = screen.getByText('Win in 28 moves or fewer').closest('.rounded-card')!;
    const wc = within(card as HTMLElement);

    // First tap arms the card; nothing commits until the confirm underneath.
    fireEvent.click(wc.getByRole('button', { name: 'Join pool' }));
    expect(enterMutate).not.toHaveBeenCalled();

    // The confirm button carries the selected amount (default middle preset $10).
    fireEvent.click(wc.getByRole('button', { name: 'Confirm · $10.00' }));
    expect(enterMutate).toHaveBeenCalledWith({
      game: 'chess.lichess',
      metric: 'chess_moves',
      difficulty: 'medium',
      entry_preset_cents: 1000,
    });

    // Changing the entry inside the card changes what gets joined.
    fireEvent.click(wc.getByRole('tab', { name: '$25.00' }));
    fireEvent.click(wc.getByRole('button', { name: 'Join pool' }));
    fireEvent.click(wc.getByRole('button', { name: 'Confirm · $25.00' }));
    expect(enterMutate).toHaveBeenLastCalledWith({
      game: 'chess.lichess',
      metric: 'chess_moves',
      difficulty: 'medium',
      entry_preset_cents: 2500,
    });
  });

  it('shows the formed room banner with the room bar', () => {
    mockStatus({
      status: 'formed',
      pool: {
        id: 'p1',
        game: 'chess.lichess',
        metric: 'chess_moves',
        metric_label: 'Moves to win',
        difficulty: 'medium',
        room_bar: 30,
        your_bar: 28,
        bar_delta: 2,
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
    expect(screen.getByText(/Win in 30 moves or fewer/)).toBeInTheDocument();
    expect(screen.getByText(/4 players · pot \$40.00/)).toBeInTheDocument();
    expect(screen.getByTestId('room-play-cue')).toHaveTextContent(
      /play your next game on lichess and win in 30 moves or fewer/i,
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
