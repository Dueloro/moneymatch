import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

describe('WagerCard fee disclosure (rake always visible pre-commit)', () => {
  it('renders the fee note for the default (middle) entry', () => {
    render(
      <WagerCard
        {...base}
        feeNote={(entry) => `${(entry / 100).toFixed(2)} platform fee`}
      />,
    );
    // Middle preset (2500) is selected by default.
    expect(screen.getByText('25.00 platform fee')).toBeInTheDocument();
  });

  it('recomputes the fee when the entry changes', async () => {
    const user = userEvent.setup();
    render(
      <WagerCard
        {...base}
        feeNote={(entry) => `${(entry / 100).toFixed(2)} platform fee`}
      />,
    );
    await user.click(screen.getByRole('tab', { name: '$50.00' }));
    expect(screen.getByText('50.00 platform fee')).toBeInTheDocument();
    expect(screen.queryByText('25.00 platform fee')).not.toBeInTheDocument();
  });
});
