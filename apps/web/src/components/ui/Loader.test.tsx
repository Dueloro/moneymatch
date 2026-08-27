import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Loader } from './Loader';

describe('Loader', () => {
  it('exposes a labelled status region for assistive tech', () => {
    render(<Loader />);
    const status = screen.getByRole('status');
    expect(status).toHaveAccessibleName('Loading');
    expect(screen.getByText('Loading')).toBeInTheDocument();
  });

  it('accepts a custom label', () => {
    render(<Loader label="Churning" />);
    expect(screen.getByRole('status')).toHaveAccessibleName('Churning');
  });

  it('shows an elapsed-time readout when motion is allowed', () => {
    // test/setup mocks matchMedia to matches:false → motion allowed
    render(<Loader />);
    expect(screen.getByText(/^\d+\.\d+s$/)).toBeInTheDocument();
  });
});
