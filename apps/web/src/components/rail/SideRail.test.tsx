import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../test/testUtils';
import { SideRail } from './SideRail';

vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({ session: null }),
}));
vi.mock('../../hooks/usePools', async () => {
  const actual =
    await vi.importActual<typeof import('../../hooks/usePools')>(
      '../../hooks/usePools',
    );
  return { ...actual, usePoolStatus: vi.fn(), useLeavePool: vi.fn() };
});

import { useLeavePool, usePoolStatus } from '../../hooks/usePools';

function mockStatus(s: unknown) {
  vi.mocked(usePoolStatus).mockReturnValue({ data: s } as ReturnType<
    typeof usePoolStatus
  >);
}

const FORMED = {
  status: 'formed',
  pool: {
    id: 'p1',
    game: 'chess.lichess',
    metric: 'chess_moves',
    metric_label: 'Moves to win',
    difficulty: 'medium',
    room_bar: 32,
    your_bar: 34,
    bar_delta: -2,
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
};

describe('SideRail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStatus({ status: 'idle', pool: null });
    vi.mocked(useLeavePool).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useLeavePool>);
  });

  it('stacks the board as balance, then one In play section', () => {
    renderWithProviders(<SideRail />);
    expect(screen.getByText('Balance')).toBeInTheDocument();
    expect(
      screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent),
    ).toEqual(['In play']);
  });

  it('shows the formed room in the rail, not above the grid', () => {
    mockStatus(FORMED);
    renderWithProviders(<SideRail />);
    const card = screen.getByTestId('rail-room-card');
    expect(card).toHaveTextContent('medium Moves to win');
    expect(card).toHaveTextContent('Room bar 32');
    expect(card).toHaveTextContent('need −2');
    expect(card).toHaveTextContent('4 players · pot $40.00');
    expect(screen.getByTestId('rail-room-play-cue')).toHaveTextContent(
      /play your next game on lichess/i,
    );
  });

  it('reflects a cleared live result instead of the play cue', () => {
    mockStatus({
      ...FORMED,
      pool: { ...FORMED.pool, your_cleared: true, your_current: 28 },
    });
    renderWithProviders(<SideRail />);
    expect(screen.getByTestId('rail-room-live')).toHaveTextContent(/Cleared/);
    expect(screen.queryByTestId('rail-room-play-cue')).not.toBeInTheDocument();
  });

  it('keeps the section in place with a cue when no room is running', () => {
    renderWithProviders(<SideRail />);
    expect(screen.queryByTestId('rail-room-card')).not.toBeInTheDocument();
    expect(screen.getByText(/Nothing running/)).toBeInTheDocument();
  });

  it('moves a formed room into In play rather than a section beside it', () => {
    mockStatus(FORMED);
    renderWithProviders(<SideRail />);
    const inPlay = screen
      .getAllByRole('heading', { level: 3 })
      .find((h) => h.textContent === 'In play')!;
    expect(inPlay.closest('section')).toContainElement(
      screen.getByTestId('rail-room-card'),
    );
    expect(screen.queryByText(/Nothing running/)).not.toBeInTheDocument();
  });

  it('separates queuing from in play, with a cancel while forming', () => {
    mockStatus({ status: 'searching', pool: null });
    renderWithProviders(<SideRail />);

    const headings = screen
      .getAllByRole('heading', { level: 3 })
      .map((h) => h.textContent);
    expect(headings).toEqual(['Queuing', 'In play']);

    expect(screen.getByTestId('rail-pool-status')).toHaveTextContent(
      'Finding your pool room',
    );
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByText(/lands here once it forms/)).toBeInTheDocument();
  });

  it('drops the Queuing section once the room has formed', () => {
    mockStatus(FORMED);
    renderWithProviders(<SideRail />);
    expect(
      screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent),
    ).toEqual(['In play']);
    expect(screen.queryByTestId('rail-pool-status')).not.toBeInTheDocument();
    expect(screen.getByTestId('rail-room-card')).toBeInTheDocument();
  });
});
