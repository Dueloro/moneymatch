import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { WalletPage } from './WalletPage';

vi.mock('../hooks/useWallet', async () => {
  const actual =
    await vi.importActual<typeof import('../hooks/useWallet')>('../hooks/useWallet');
  return {
    ...actual,
    useWallet: vi.fn(),
    useWalletLedger: vi.fn(),
    useDemoDeposit: vi.fn(),
    useDemoWithdrawal: vi.fn(),
  };
});

import {
  useDemoDeposit,
  useDemoWithdrawal,
  useWallet,
  useWalletLedger,
} from '../hooks/useWallet';

const depositMutate = vi.fn();
const withdrawMutate = vi.fn();

describe('WalletPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useWallet).mockReturnValue({
      data: {
        currency: 'DEMO',
        available_cents: 100_000,
        escrow_cents: 2_600,
        lifetime_net_cents: 6_894,
        recent: [],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useWallet>);
    vi.mocked(useWalletLedger).mockReturnValue({
      data: {
        pages: [
          {
            entries: [
              {
                id: 'e1',
                entry_type: 'demo_deposit',
                amount_cents: 100_000,
                escrow_delta_cents: 0,
                ref_type: 'demo_rail',
                ref_id: null,
                balance_after_cents: 100_000,
                memo: 'signup grant',
                created_at: new Date().toISOString(),
              },
            ],
          },
        ],
      },
      hasNextPage: false,
      isFetchingNextPage: false,
      fetchNextPage: vi.fn(),
    } as unknown as ReturnType<typeof useWalletLedger>);
    vi.mocked(useDemoDeposit).mockReturnValue({
      mutate: depositMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useDemoDeposit>);
    vi.mocked(useDemoWithdrawal).mockReturnValue({
      mutate: withdrawMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useDemoWithdrawal>);
  });

  it('renders the stat bar with live balances', () => {
    renderWithProviders(<WalletPage />);
    expect(screen.getByText('Available')).toBeInTheDocument();
    expect(screen.getByText('$1,000.00')).toBeInTheDocument();
    expect(screen.getByText('$26.00')).toBeInTheDocument(); // escrow
    expect(screen.getByText('+$68.94')).toBeInTheDocument(); // lifetime, green
  });

  it('shows the signup grant ledger row', () => {
    renderWithProviders(<WalletPage />);
    expect(screen.getByText('signup grant')).toBeInTheDocument();
  });

  it('fires a preset deposit on click', () => {
    renderWithProviders(<WalletPage />);
    fireEvent.click(screen.getAllByRole('button', { name: '$25.00' })[0]);
    expect(depositMutate).toHaveBeenCalledWith(2500);
  });
});
