import { render, screen } from '@testing-library/react';
import { act } from 'react';
import { describe, expect, it } from 'vitest';

import { AnimatedBalance } from './AnimatedBalance';

describe('AnimatedBalance', () => {
  it('says nothing on first render', () => {
    render(<AnimatedBalance cents={10_000} testId="bal" />);
    expect(screen.queryByTestId('bal-delta')).not.toBeInTheDocument();
  });

  it('shows a skeleton, not a dash, while the balance is still loading', () => {
    render(<AnimatedBalance cents={undefined} testId="bal" />);
    expect(screen.getByTestId('bal')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByTestId('bal-skeleton')).toBeInTheDocument();
    expect(screen.getByTestId('bal')).not.toHaveTextContent('—');
    expect(screen.queryByTestId('bal-delta')).not.toBeInTheDocument();
  });

  it('tints a gain in lime (money), not cyan', () => {
    const { rerender } = render(<AnimatedBalance cents={10_000} testId="bal" />);
    act(() => rerender(<AnimatedBalance cents={14_500} testId="bal" />));
    expect(screen.getByTestId('bal-delta')).toHaveClass('text-green');
    expect(screen.getByTestId('bal-delta')).not.toHaveClass('text-live');
  });

  it('does not fire a gain when the balance first loads (loading → value)', () => {
    const { rerender } = render(<AnimatedBalance cents={undefined} testId="bal" />);
    act(() => rerender(<AnimatedBalance cents={101_000} testId="bal" />));
    expect(screen.queryByTestId('bal-delta')).not.toBeInTheDocument();
    expect(screen.getByTestId('bal')).toHaveTextContent('101,000 pts');
  });

  it('shows what was won when the balance rises', () => {
    const { rerender } = render(<AnimatedBalance cents={10_000} testId="bal" />);
    act(() => rerender(<AnimatedBalance cents={14_500} testId="bal" />));
    expect(screen.getByTestId('bal-delta')).toHaveTextContent('+4,500 pts');
  });

  it('shows what was lost when it falls, and marks the direction', () => {
    const { rerender } = render(<AnimatedBalance cents={10_000} testId="bal" />);
    act(() => rerender(<AnimatedBalance cents={7_500} testId="bal" />));
    const delta = screen.getByTestId('bal-delta');
    expect(delta).toHaveTextContent('2,500 pts');
    expect(delta).not.toHaveTextContent('+');
  });

  it('marks direction on the figure itself, not only in colour', () => {
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
    const { rerender } = render(<AnimatedBalance cents={10_000} testId="bal" />);
    act(() => rerender(<AnimatedBalance cents={10_000} testId="bal" />));
    expect(screen.queryByTestId('bal-delta')).not.toBeInTheDocument();
  });

  it('keeps the amount out of the accessibility tree twice over', () => {
    const { rerender } = render(<AnimatedBalance cents={10_000} testId="bal" />);
    act(() => rerender(<AnimatedBalance cents={11_000} testId="bal" />));
    expect(screen.getByTestId('bal-delta')).toHaveAttribute('aria-hidden');
  });
});
