import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { WagerCard } from './WagerCard';

const base = {
  gameName: 'Counter Strike 2',
  title: 'Medium K/D ratio',
  entryOptions: [1000, 2500, 5000],
  payoutFor: (cents: number) => cents * 3,
  payoutLabel: 'Pot if full',
  capacity: 4,
  buttonLabel: 'Join pool',
  onJoin: vi.fn(),
};

describe('WagerCard fill count', () => {
  it('shows a synthetic count only when `filled` is provided (demo)', () => {
    render(<WagerCard {...base} filled={2} />);
    expect(screen.getByText('2 of 4 in')).toBeInTheDocument();
  });

  it('shows no fabricated count in production (filled omitted)', () => {
    render(<WagerCard {...base} />);
    expect(screen.queryByText(/of 4 in/)).not.toBeInTheDocument();
  });

  it('shows 1v1 for head-to-head regardless of fill', () => {
    render(<WagerCard {...base} oneVsOne />);
    expect(screen.getByText('1v1')).toBeInTheDocument();
    expect(screen.queryByText(/of 4 in/)).not.toBeInTheDocument();
  });
});
