import { render, screen } from '@testing-library/react';
import { act } from 'react';
import { describe, expect, it } from 'vitest';

import { AnimatedBalance } from './AnimatedBalance';

/**
 * Settlement is the moment the product does its job. It used to arrive as a
 * number that was merely different from the one before, so you had to remember
 * the old one to know whether you had won.
 */
describe('AnimatedBalance', () => {
  it('says nothing on first render', () => {
    // Otherwise opening any page announces your whole balance as a win.
    render(<AnimatedBalance cents={10_000} testId="bal" />);
    expect(screen.queryByTestId('bal-delta')).not.toBeInTheDocument();
  });

  it('shows a placeholder while the balance is still loading', () => {
    render(<AnimatedBalance cents={undefined} testId="bal" />);
    expect(screen.getByTestId('bal')).toHaveTextContent('—');
    expect(screen.queryByTestId('bal-delta')).not.toBeInTheDocument();
  });

  it('does not fire a gain when the balance first loads (loading → value)', () => {
    // The bug: 0-while-loading → real value announced a phantom "+$X" gain on
    // every login/refresh. Loading is not a settlement, so nothing animates and
    // the real figure renders directly (no $0 flash, no count-up from zero).
    const { rerender } = render(<AnimatedBalance cents={undefined} testId="bal" />);
    act(() => rerender(<AnimatedBalance cents={101_000} testId="bal" />));
    expect(screen.queryByTestId('bal-delta')).not.toBeInTheDocument();
    expect(screen.getByTestId('bal')).toHaveTextContent('$1,010.00');
  });

  it('shows what was won when the balance rises', () => {
    const { rerender } = render(<AnimatedBalance cents={10_000} testId="bal" />);
    act(() => rerender(<AnimatedBalance cents={14_500} testId="bal" />));
    expect(screen.getByTestId('bal-delta')).toHaveTextContent('+$45.00');
  });

  it('shows what was lost when it falls, and marks the direction', () => {
    const { rerender } = render(<AnimatedBalance cents={10_000} testId="bal" />);
    act(() => rerender(<AnimatedBalance cents={7_500} testId="bal" />));
    const delta = screen.getByTestId('bal-delta');
    expect(delta).toHaveTextContent('$25.00');
    expect(delta).not.toHaveTextContent('+');
  });

  it('marks direction on the figure itself, not only in colour', () => {
    // Colour alone is not a signal everyone receives. The figure is still
    // counting toward its new value at this point, so the marker is what
    // carries the direction, not the digits.
    const { rerender } = render(<AnimatedBalance cents={10_000} testId="bal" />);
    act(() => rerender(<AnimatedBalance cents={12_000} testId="bal" />));
    expect(
      screen.getByTestId('bal').querySelector('[data-direction="up"]'),
    ).toBeInTheDocument();

    const { rerender: rerenderDown } = render(
      <AnimatedBalance cents={10_000} testId="down" />,
    );
    act(() => rerenderDown(<AnimatedBalance cents={9_000} testId="down" />));
    expect(
      screen.getByTestId('down').querySelector('[data-direction="down"]'),
    ).toBeInTheDocument();
  });

  it('stays quiet when a refetch returns the same balance', () => {
    // The wallet is polled; an unchanged answer is not an event.
    const { rerender } = render(<AnimatedBalance cents={10_000} testId="bal" />);
    act(() => rerender(<AnimatedBalance cents={10_000} testId="bal" />));
    expect(screen.queryByTestId('bal-delta')).not.toBeInTheDocument();
  });

  it('keeps the amount out of the accessibility tree twice over', () => {
    // The figure beside it is already announced; a number mid-flight is noise.
    const { rerender } = render(<AnimatedBalance cents={10_000} testId="bal" />);
    act(() => rerender(<AnimatedBalance cents={11_000} testId="bal" />));
    expect(screen.getByTestId('bal-delta')).toHaveAttribute('aria-hidden');
  });
});
