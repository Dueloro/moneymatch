import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ClearBar } from './ClearBar';

describe('ClearBar, higher is better', () => {
  it('shows the gap to reach the bar', () => {
    render(<ClearBar current={1.5} target={1.8} />);
    expect(screen.getByText('need +0.30')).toBeInTheDocument();
  });

  it('says clear once at or over the bar', () => {
    render(<ClearBar current={2} target={1.8} />);
    expect(screen.getByText('clear')).toBeInTheDocument();
  });
});

describe('ClearBar, lower is better (moves to win)', () => {
  it('shows the moves still to shave when over the bar', () => {
    render(<ClearBar current={34} target={30} lowerIsBetter />);
    expect(screen.getByText('need −4')).toBeInTheDocument();
    expect(screen.queryByText(/need \+/)).not.toBeInTheDocument();
  });

  it('says how far under the bar you are', () => {
    render(<ClearBar current={26} target={30} lowerIsBetter />);
    expect(screen.getByText('4 under')).toBeInTheDocument();
    expect(screen.queryByText(/need/)).not.toBeInTheDocument();
  });

  it('says clear exactly on the bar', () => {
    render(<ClearBar current={30} target={30} lowerIsBetter />);
    expect(screen.getByText('clear')).toBeInTheDocument();
  });

  it('shades the excess past the bar, not a gap before it', () => {
    const { container } = render(<ClearBar current={34} target={30} lowerIsBetter />);
    expect(container.querySelector('[data-testid="clear-gap"]')).not.toBeNull();
  });

  it('shades nothing once under the bar', () => {
    const { container } = render(<ClearBar current={26} target={30} lowerIsBetter />);
    expect(container.querySelector('[data-testid="clear-gap"]')).toBeNull();
  });
});
