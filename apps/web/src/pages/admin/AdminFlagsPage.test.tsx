import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../test/testUtils';
import { AdminFlagsPage } from './AdminFlagsPage';

vi.mock('../../hooks/useAdmin', async () => {
  const actual =
    await vi.importActual<typeof import('../../hooks/useAdmin')>(
      '../../hooks/useAdmin',
    );
  return { ...actual, useAdminFlags: vi.fn(), useUpdateFlag: vi.fn() };
});

import { useAdminFlags, useUpdateFlag } from '../../hooks/useAdmin';

const mutate = vi.fn();

describe('AdminFlagsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useUpdateFlag).mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useUpdateFlag>);
  });

  it('renders kill-switch rows and toggles a flag', async () => {
    vi.mocked(useAdminFlags).mockReturnValue({
      data: [
        { key: 'settlement_paused', enabled: false, payload: {} },
        { key: 'queue_paused', enabled: true, payload: {} },
        { key: 'geo_config', enabled: true, payload: { excluded_states: ['WA'] } },
      ],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useAdminFlags>);

    renderWithProviders(<AdminFlagsPage />);
    expect(screen.getByText('settlement_paused')).toBeInTheDocument();

    // The settlement_paused row (enabled=false) offers "Enable".
    const enableButtons = screen.getAllByText('Enable');
    await userEvent.click(enableButtons[0]);
    expect(mutate).toHaveBeenCalledWith({ key: 'settlement_paused', enabled: true });
  });

  it('saves the geo_config excluded-state list', async () => {
    vi.mocked(useAdminFlags).mockReturnValue({
      data: [{ key: 'geo_config', enabled: true, payload: { excluded_states: [] } }],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useAdminFlags>);

    renderWithProviders(<AdminFlagsPage />);
    const input = screen.getByDisplayValue('');
    await userEvent.type(input, 'wa, id');
    await userEvent.click(screen.getByText('Save geo_config'));
    expect(mutate).toHaveBeenCalledWith(
      { key: 'geo_config', payload: { excluded_states: ['WA', 'ID'] } },
      expect.anything(),
    );
  });
});
