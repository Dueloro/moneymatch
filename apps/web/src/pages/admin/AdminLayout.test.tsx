import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '../../test/testUtils';
import { AdminLayout } from './AdminLayout';
import { styles } from './adminStyles';

describe('AdminLayout', () => {
  it('sets its own background and ink instead of inheriting the dark app body', () => {
    renderWithProviders(<AdminLayout />, { route: '/admin/users' });
    const root = screen.getByTestId('admin-root');
    expect(root).toHaveStyle({ background: '#fff', color: '#111' });
    expect(screen.getByText('Money Match admin')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Users' })).toHaveStyle({ color: '#fff' });
    expect(screen.getByRole('link', { name: 'Risk' })).toHaveStyle({ color: '#111' });
  });

  it('gives table headers, buttons and inputs explicit contrast', () => {
    for (const s of [styles.th, styles.button, styles.input]) {
      expect(s.color).toBe('#111');
      expect(s.background).toMatch(/^#/);
    }
  });
});
