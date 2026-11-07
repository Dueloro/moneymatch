import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, pts } from '../test/testUtils';
import { PoolsPage } from './PoolsPage';

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ session: null }),
}));
vi.mock('../hooks/useWallet', () => ({
  useWallet: () => ({
    data: { available_cents: 100_000, escrow_cents: 0, lifetime_net_cents: 0 },
  }),
}));
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
    // Capped at room_size x (1 - rake).
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
    expect(screen.getAllByRole('button', { name: 'Join pool' })).toHaveLength(3);
    const card = screen.getByText('Medium · wins only').closest('.rounded-card')!;
    // The big figure is the one statement of the bar.
    expect(card).toHaveTextContent('28moves or fewer');
    expect(
      within(card as HTMLElement).queryByText(/win in 28/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('Moves to win')).not.toBeInTheDocument();
    expect(screen.getByText('20%')).toBeInTheDocument();
    expect(screen.getAllByText(pts('3,600 pts')).length).toBeGreaterThan(0);
  });

  it('confirms in the card before joining, using the selected entry', () => {
    renderWithProviders(<PoolsPage />);
    const card = screen.getByText('Medium · wins only').closest('.rounded-card')!;
    const wc = within(card as HTMLElement);

    fireEvent.click(wc.getByRole('button', { name: 'Join pool' }));
    expect(enterMutate).not.toHaveBeenCalled();

    fireEvent.click(wc.getByRole('button', { name: 'Confirm · 1,000 pts' }));
    expect(enterMutate).toHaveBeenCalledWith({
      game: 'chess.lichess',
      metric: 'chess_moves',
      difficulty: 'medium',
      entry_preset_cents: 1000,
    });

    fireEvent.click(wc.getByRole('tab', { name: '2,500 pts' }));
    fireEvent.click(wc.getByRole('button', { name: 'Join pool' }));
    fireEvent.click(wc.getByRole('button', { name: 'Confirm · 2,500 pts' }));
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
    const room = screen.getByTestId('room-card');
    expect(room).toHaveTextContent('Medium · wins only');
    expect(room).toHaveTextContent('30moves or fewer');
    expect(room).toHaveTextContent('your bar 28 moves');
    expect(screen.getByText('2 moves under')).toBeInTheDocument();
    expect(room).toHaveTextContent('4 players · pot 4,000 pts');
    expect(screen.getByTestId('room-play-cue')).toHaveTextContent(
      /play your next game on lichess/i,
    );
  });

  it('the filter menu is collapsed until the hamburger toggle is clicked', () => {
    renderWithProviders(<PoolsPage />);
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
