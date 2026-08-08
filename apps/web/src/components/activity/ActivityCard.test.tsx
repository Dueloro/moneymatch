import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '../../test/testUtils';
import type { ActivityItem } from '../../hooks/useActivity';
import { ActivityCard } from './ActivityCard';

function match(overrides: Partial<ActivityItem> = {}): ActivityItem {
  return {
    type: 'match',
    id: 'm1',
    game: 'cs2.faceit',
    market: 'kd_ratio',
    market_label: 'K/D ratio',
    kind: 'stat_race',
    state: 'SETTLED',
    entry_cents: 1000,
    title: null,
    net_cents: 800,
    opponent_username: 's1mple_fan',
    your_stat_line: { cs2_kd_ratio: 1.63, game_id: 'g' },
    opponent_stat_line: { cs2_kd_ratio: 1.11, game_id: 'g' },
    live: null,
    detail: {
      kind: 'match',
      game: 'cs2.faceit',
      opponent: 's1mple_fan',
      entry_cents: 1000,
      prize_cents: 1800,
      map: 'de_dust2',
      mode: 'Competitive',
      your_stats: { 'K/D': 1.63, Kills: 31 },
      opponent_stats: { 'K/D': 1.11, Kills: 24 },
    },
    dispute_status: null,
    created_at: new Date().toISOString(),
    resolved_at: new Date().toISOString(),
    ...overrides,
  };
}

describe('ActivityCard', () => {
  it('names the host game on the row', () => {
    renderWithProviders(<ActivityCard item={match()} />);
    // The CS2 match carries a game badge so the row is not game-ambiguous.
    expect(screen.getByText('Counter Strike')).toBeInTheDocument();
  });

  it('expands to show per-match stats and a contest action', () => {
    renderWithProviders(<ActivityCard item={match()} />);
    // Collapsed: detail not shown yet.
    expect(screen.queryByText('de_dust2')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /details/i }));

    expect(screen.getByText('de_dust2 · Competitive')).toBeInTheDocument();
    // Stat table shows the shared keys with your + opponent values.
    expect(screen.getByText('Kills')).toBeInTheDocument();
    expect(screen.getByText('31')).toBeInTheDocument();
    expect(screen.getByText('24')).toBeInTheDocument();
    // A settled contest can be contested.
    expect(
      screen.getByRole('button', { name: 'Contest this result' }),
    ).toBeInTheDocument();
  });

  it('opens the contest form when the action is clicked', () => {
    renderWithProviders(<ActivityCard item={match()} />);
    fireEvent.click(screen.getByRole('button', { name: /details/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Contest this result' }));
    expect(
      screen.getByPlaceholderText(/last round wasn't counted/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Submit for review' }),
    ).toBeInTheDocument();
  });

  it('shows the review status once contested', () => {
    renderWithProviders(<ActivityCard item={match({ dispute_status: 'open' })} />);
    fireEvent.click(screen.getByRole('button', { name: /details/i }));
    expect(screen.getByText('Contested · under review')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Contest this result' }),
    ).not.toBeInTheDocument();
  });
});
