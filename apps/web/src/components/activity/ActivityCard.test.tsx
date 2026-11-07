import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '../../test/testUtils';
import type { ActivityItem } from '../../hooks/useActivity';
import { ActivityCard } from './ActivityCard';

function match(overrides: Partial<ActivityItem> = {}): ActivityItem {
  return {
    type: 'match',
    id: 'm1',
    game: 'chess.lichess',
    market: 'win_h2h',
    market_label: 'Win the game',
    kind: 'win_h2h',
    state: 'SETTLED',
    entry_cents: 1000,
    title: null,
    net_cents: 800,
    opponent_username: 'knight_rider',
    your_stat_line: { result: 1, game_id: 'g' },
    opponent_stat_line: { result: 0, game_id: 'g' },
    live: null,
    detail: {
      kind: 'match',
      game: 'chess.lichess',
      opponent: 'knight_rider',
      entry_cents: 1000,
      prize_cents: 1800,
      host_game_id: 'abcd1234',
      your_stats: { Moves: 31, Accuracy: 88 },
      opponent_stats: { Moves: 31, Accuracy: 74 },
    },
    dispute_status: null,
    created_at: new Date().toISOString(),
    resolved_at: new Date().toISOString(),
    ...overrides,
  };
}

describe('ActivityCard', () => {
  it('expands to show per-match stats and a contest action', () => {
    renderWithProviders(<ActivityCard item={match()} />);
    expect(screen.queryByText('abcd1234')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /details/i }));

    expect(screen.getByRole('link', { name: 'abcd1234' })).toHaveAttribute(
      'href',
      'https://lichess.org/abcd1234',
    );
    expect(screen.getByText('Accuracy')).toBeInTheDocument();
    expect(screen.getByText('88')).toBeInTheDocument();
    expect(screen.getByText('74')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Contest this result' }),
    ).toBeInTheDocument();
  });

  it('opens the contest form when the action is clicked', () => {
    renderWithProviders(<ActivityCard item={match()} />);
    fireEvent.click(screen.getByRole('button', { name: /details/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Contest this result' }));
    expect(screen.getByPlaceholderText(/my game wasn't counted/i)).toBeInTheDocument();
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
