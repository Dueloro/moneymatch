import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AmountText } from './AmountText';

describe('AmountText', () => {
  it('sets money in the numeric face', () => {
    render(<AmountText cents={1800} testId="amt" />);
    expect(screen.getByTestId('amt')).toHaveClass('num');
    expect(screen.getByTestId('amt')).toHaveTextContent('+1,800 pts');
  });

  it('is lime for a win, grey for a loss, and always lime for a money figure', () => {
    render(
      <>
        <AmountText cents={1800} win testId="win" />
        <AmountText cents={-1000} testId="loss" />
        <AmountText cents={0} signed={false} money testId="bal" />
      </>,
    );
    expect(screen.getByTestId('win')).toHaveClass('text-green');
    expect(screen.getByTestId('loss')).toHaveClass('text-text-secondary');
    expect(screen.getByTestId('bal')).toHaveClass('text-green');
    expect(screen.getByTestId('bal')).toHaveTextContent('0 pts');
  });
});
