import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../test/testUtils';
import { AdminReconciliationPage } from './AdminReconciliationPage';

vi.mock('../../hooks/useAdmin', async () => {
  const actual =
    await vi.importActual<typeof import('../../hooks/useAdmin')>(
      '../../hooks/useAdmin',
    );
  return { ...actual, useReconciliation: vi.fn() };
});

import { useReconciliation } from '../../hooks/useAdmin';

describe('AdminReconciliationPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows a clean book and a stale worker', () => {
    vi.mocked(useReconciliation).mockReturnValue({
      data: {
        ok: true,
        solvency_ok: true,
        solvency_violations: [],
        totals: { user_total: 100000, promo_funding: 100000, rake: 0 },
        contest_violations: [],
        worker: { heartbeat_at: null, stale: true },
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useReconciliation>);

    renderWithProviders(<AdminReconciliationPage />);
    expect(screen.getByText('OK')).toBeInTheDocument();
    expect(screen.getByText('No contest breaches.')).toBeInTheDocument();
    expect(screen.getByText(/STALE/)).toBeInTheDocument();
  });

  it('renders a per-contest conservation breach in red', () => {
    vi.mocked(useReconciliation).mockReturnValue({
      data: {
        ok: false,
        solvency_ok: true,
        solvency_violations: [],
        totals: {},
        contest_violations: [
          { ref_type: 'match', ref_id: 'abcdef1234', violations: ['breach x'] },
        ],
        worker: { heartbeat_at: '2026-07-17T00:00:00Z', stale: false },
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useReconciliation>);

    renderWithProviders(<AdminReconciliationPage />);
    expect(screen.getByText('VIOLATIONS')).toBeInTheDocument();
    expect(screen.getByText('breach x')).toBeInTheDocument();
  });
});
