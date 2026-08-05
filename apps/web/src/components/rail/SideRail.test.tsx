import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../test/testUtils';
import { SideRail } from './SideRail';

// No session, so wallet/activity/queue stay disabled and fall to their empty
// states. The pool status is the thing under test, so drive it directly.
vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({ isDemo: false, session: null }),
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

  it('stacks the board as balance, in play, queue, then room formed', () => {
    renderWithProviders(<SideRail />);
    expect(screen.getByText('Balance')).toBeInTheDocument();
    expect(
      screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent),
    ).toEqual(['In play', 'Queue', 'Room formed']);
  });

  it('shows the formed room in the rail, not above the grid', () => {
    mockStatus(FORMED);
    renderWithProviders(<SideRail />);
    const card = screen.getByTestId('rail-room-card');
    expect(card).toHaveTextContent('medium K/D ratio');
    expect(card).toHaveTextContent('Room bar 1.75');
    expect(card).toHaveTextContent('4 players · pot $40.00');
    expect(screen.getByTestId('rail-room-play-cue')).toHaveTextContent(
      /you can now play your .* game/i,
    );
  });

  it('keeps the section in place with a cue when no room is running', () => {
    renderWithProviders(<SideRail />);
    expect(screen.queryByTestId('rail-room-card')).not.toBeInTheDocument();
    expect(screen.getByText(/No room yet/)).toBeInTheDocument();
  });

  it('offers a cancel while the room is still forming', () => {
    mockStatus({ status: 'searching', pool: null });
    renderWithProviders(<SideRail />);
    expect(screen.getByTestId('rail-pool-status')).toHaveTextContent(
      'Finding your room',
    );
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });
});
