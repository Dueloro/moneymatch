import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, pts } from '../test/testUtils';
import { WalletPage } from './WalletPage';

vi.mock('../hooks/useWallet', async () => {
  const actual =
    await vi.importActual<typeof import('../hooks/useWallet')>('../hooks/useWallet');
  return {
    ...actual,
    useWallet: vi.fn(),
    useWalletLedger: vi.fn(),
    usePlayMoneyDeposit: vi.fn(),
  };
});

import { usePlayMoneyDeposit, useWallet, useWalletLedger } from '../hooks/useWallet';

const depositMutate = vi.fn();

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
    vi.mocked(usePlayMoneyDeposit).mockReturnValue({
      mutate: depositMutate,
      isPending: false,
    } as unknown as ReturnType<typeof usePlayMoneyDeposit>);
  });

  it('leads with available balance, with escrow and lifetime as context', () => {
    renderWithProviders(<WalletPage />);
    expect(screen.getByText('Available')).toBeInTheDocument();
    expect(screen.getByTestId('wallet-balance')).toHaveTextContent('100,000 pts');
    expect(screen.getByText(pts('2,600 pts'))).toBeInTheDocument();
    expect(screen.getByText(pts('+6,894 pts'))).toBeInTheDocument();
    expect(screen.getByText('Points have no cash value.')).toBeInTheDocument();
  });

  it('labels the signup grant as welcome points', () => {
    renderWithProviders(<WalletPage />);
    expect(screen.getByText('Welcome points')).toBeInTheDocument();
  });

  it('adds points only after the confirm step', () => {
    renderWithProviders(<WalletPage />);
    expect(screen.getByRole('button', { name: 'Add points' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '2,500 pts' }));
    expect(depositMutate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Add 2,500 pts' }));
    expect(depositMutate).toHaveBeenCalledWith(2500, expect.anything());
  });

  it('can back out of a selection', () => {
    renderWithProviders(<WalletPage />);
    fireEvent.click(screen.getByRole('button', { name: '2,500 pts' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('button', { name: 'Add points' })).toBeDisabled();
  });

  it('does not offer a cash-out', () => {
    renderWithProviders(<WalletPage />);
    expect(screen.queryByText(/cash out/i)).not.toBeInTheDocument();
  });
});
