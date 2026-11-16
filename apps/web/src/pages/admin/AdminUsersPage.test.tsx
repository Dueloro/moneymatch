import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../test/testUtils';
import { AdminUsersPage } from './AdminUsersPage';

const freeze = vi.fn();
let status = 'active';

vi.mock('../../hooks/useAdmin', () => ({
  useAdminUsers: () => ({
    isLoading: false,
    isError: false,
    data: [{ id: 'u1', username: 'kvem_', email: null, status, role: 'user' }],
  }),
  useAdminUser: () => ({
    isLoading: false,
    isError: false,
    data: {
      id: 'u1',
      username: 'kvem_',
      status,
      available_cents: 0,
      escrow_cents: 0,
      lifetime_net_cents: 0,
      linked_accounts: [],
      contests: [],
      recent_ledger: [],
    },
  }),
  useFreezeUser: () => ({ mutate: freeze }),
  useAdjustUser: () => ({ mutate: vi.fn() }),
}));

function open() {
  renderWithProviders(<AdminUsersPage />);
  fireEvent.click(screen.getByRole('button', { name: 'Open' }));
}

describe('AdminUsersPage', () => {
  it('freezes an active user', () => {
    status = 'active';
    open();
    fireEvent.click(screen.getByRole('button', { name: 'Freeze' }));
    expect(freeze).toHaveBeenCalledWith(true);
  });

  it('does not offer to unfreeze a self-excluded user', () => {
    status = 'self_excluded';
    open();
    expect(screen.queryByRole('button', { name: 'Unfreeze' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Self-excluded' })).toBeDisabled();
  });
});
