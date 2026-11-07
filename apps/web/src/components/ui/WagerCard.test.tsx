import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { WagerCard } from './WagerCard';

const base = {
  gameName: 'Moves to win',
  title: 'Win in 28 moves or fewer',
  entryOptions: [1000, 2500, 5000],
  payoutFor: (cents: number) => cents * 3,
  payoutLabel: 'Pot if full',
  buttonLabel: 'Join pool',
  onJoin: vi.fn(),
};

describe('WagerCard fill count', () => {
  it('never shows a seat count', () => {
    render(<WagerCard {...base} />);
    expect(screen.queryByText(/of 4 in/)).not.toBeInTheDocument();
  });

  it('shows 1v1 for head-to-head', () => {
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
    await user.click(screen.getByRole('tab', { name: '5,000 pts' }));
    expect(screen.getByText('50.00 platform fee')).toBeInTheDocument();
    expect(screen.queryByText('25.00 platform fee')).not.toBeInTheDocument();
  });
});
