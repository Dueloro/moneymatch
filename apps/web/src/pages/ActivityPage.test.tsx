import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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
    game: 'cs2.faceit',
    market: 'kd_ratio',
    market_label: 'K/D ratio',
    kind: 'stat_race',
    state: 'ACTIVE',
    entry_cents: 1000,
    title: null,
    net_cents: null,
    opponent_username: 'kvem_',
    your_stat_line: null,
    opponent_stat_line: null,
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

  it('shows a won stat-race with the signed prize and stat line', () => {
    mockItems([
      item({
        state: 'SETTLED',
        net_cents: 800,
        resolved_at: new Date().toISOString(),
        your_stat_line: { cs2_kd_ratio: 1.5, game_id: 'g1' },
        opponent_stat_line: { cs2_kd_ratio: 1.1, game_id: 'g2' },
      }),
    ]);
    renderWithProviders(<ActivityPage />);
    expect(screen.getByText('vs kvem_ · K/D ratio')).toBeInTheDocument();
    expect(screen.getByText(/Won/)).toBeInTheDocument();
    expect(screen.getByText(/You 1.5 · kvem_ 1.1/)).toBeInTheDocument();
    expect(screen.getByText('+$8.00')).toBeInTheDocument(); // signed net, green
  });

  it('renders a settled pool row from its title, not an opponent', () => {
    mockItems([
      item({
        type: 'pool',
        id: 'pool1',
        title: 'K/D ratio · Medium pool',
        state: 'SETTLED',
        net_cents: 800,
        opponent_username: null,
        resolved_at: new Date().toISOString(),
      }),
    ]);
    renderWithProviders(<ActivityPage />);
    expect(screen.getByText('K/D ratio · Medium pool')).toBeInTheDocument();
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

  it('pops a settlement toast when a match newly resolves', () => {
    // First paint: the match is still live (seeds the "seen" set as empty).
    mockItems([item({ id: 'm9', state: 'ACTIVE', net_cents: null })]);
    const { rerender } = renderWithProviders(<ActivityPage />);
    expect(screen.queryByTestId('settlement-toast')).not.toBeInTheDocument();

    // Next poll: it settled as a win → the toast pops.
    mockItems([
      item({
        id: 'm9',
        state: 'SETTLED',
        net_cents: 800,
        resolved_at: new Date().toISOString(),
      }),
    ]);
    rerender(<ActivityPage />);
    expect(screen.getByTestId('settlement-toast')).toHaveTextContent(
      'You won $8.00 vs kvem_',
    );
  });
});
