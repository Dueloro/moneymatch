import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Toaster } from '../components/ui/Toaster';
import { renderWithProviders } from '../test/testUtils';
import { ActivityPage } from './ActivityPage';

vi.mock('../hooks/useActivity', async () => {
  const actual =
    await vi.importActual<typeof import('../hooks/useActivity')>(
      '../hooks/useActivity',
    );
  return { ...actual, useActivity: vi.fn() };
});

import { useActivity, type ActivityItem } from '../hooks/useActivity';

function item(overrides: Partial<ActivityItem>): ActivityItem {
  return {
    type: 'match',
    id: 'm1',
    game: 'chess.lichess',
    market: 'win_h2h',
    market_label: 'Win the game',
    kind: 'win_h2h',
    state: 'ACTIVE',
    entry_cents: 1000,
    title: null,
    net_cents: null,
    opponent_username: 'kvem_',
    your_stat_line: null,
    opponent_stat_line: null,
    live: null,
    detail: null,
    dispute_status: null,
    created_at: new Date().toISOString(),
    resolved_at: null,
    ...overrides,
  };
}

function mockItems(items: ActivityItem[]) {
  vi.mocked(useActivity).mockReturnValue({
    data: { items },
    isLoading: false,
  } as unknown as ReturnType<typeof useActivity>);
}

describe('ActivityPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows a won match with the signed prize', () => {
    mockItems([
      item({
        state: 'SETTLED',
        net_cents: 800,
        resolved_at: new Date().toISOString(),
      }),
    ]);
    renderWithProviders(<ActivityPage />);
    expect(screen.getByText('vs kvem_ · Win the game')).toBeInTheDocument();
    expect(screen.getByText(/Won/)).toBeInTheDocument();
    expect(screen.getByText('+$8.00')).toBeInTheDocument();
  });

  it('renders a settled pool row from its title, not an opponent', () => {
    mockItems([
      item({
        type: 'pool',
        id: 'pool1',
        title: 'Moves to win · Medium pool',
        state: 'SETTLED',
        net_cents: 800,
        opponent_username: null,
        resolved_at: new Date().toISOString(),
      }),
    ]);
    renderWithProviders(<ActivityPage />);
    expect(screen.getByText('Moves to win · Medium pool')).toBeInTheDocument();
    expect(screen.getByText(/Won/)).toBeInTheDocument();
    expect(screen.getByText('+$8.00')).toBeInTheDocument();
  });

  it('labels a push as refunded and an in-flight match as in play', () => {
    mockItems([
      item({
        id: 'p',
        state: 'PUSHED',
        net_cents: 0,
        resolved_at: new Date().toISOString(),
      }),
      item({ id: 'a', state: 'ACTIVE', net_cents: null }),
    ]);
    renderWithProviders(<ActivityPage />);
    expect(screen.getByText(/Push · refunded/)).toBeInTheDocument();
    expect(screen.getByText(/In progress/)).toBeInTheDocument();
    expect(screen.getByText('$10.00 in play')).toBeInTheDocument();
  });

  it('shows a live chess line with move count and whose turn', () => {
    mockItems([
      item({
        id: 'chess1',
        game: 'chess.lichess',
        market: 'win_h2h',
        kind: 'win_h2h',
        state: 'ACTIVE',
        net_cents: null,
        live: {
          kind: 'match',
          format: 'chess',
          status: 'live',
          moves: 12,
          your_color: 'white',
          turn: 'you',
          result: null,
        },
      }),
    ]);
    renderWithProviders(<ActivityPage />);
    expect(screen.getByText('Live')).toBeInTheDocument();
    expect(screen.getByText(/move 12 · your move/)).toBeInTheDocument();
  });

  it('shows a live pool line with current stat vs the bar', () => {
    mockItems([
      item({
        type: 'pool',
        id: 'poolLive',
        title: 'Moves to win · Medium pool',
        state: 'LOCKED',
        net_cents: null,
        opponent_username: null,
        live: {
          kind: 'pool',
          label: 'Moves to win',
          status: 'cleared',
          current: 24,
          target: 30,
          cleared: true,
          matches: 1,
        },
      }),
    ]);
    renderWithProviders(<ActivityPage />);
    expect(screen.getByText(/Moves to win 24 · cleared 30/)).toBeInTheDocument();
  });

  it('pops a settlement toast when a match newly resolves', () => {
    const view = () => (
      <>
        <ActivityPage />
        <Toaster />
      </>
    );

    mockItems([item({ id: 'm9', state: 'ACTIVE', net_cents: null })]);
    const { rerender } = renderWithProviders(view());
    expect(screen.queryByText(/You won/)).not.toBeInTheDocument();

    mockItems([
      item({
        id: 'm9',
        state: 'SETTLED',
        net_cents: 800,
        resolved_at: new Date().toISOString(),
      }),
    ]);
    rerender(view());
    expect(screen.getByText('You won $8.00 vs kvem_')).toBeInTheDocument();
  });
});
