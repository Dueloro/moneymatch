import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

export interface LedgerEntry {
  id: string;
  entry_type: string;
  amount_cents: number;
  escrow_delta_cents: number;
  ref_type: string;
  ref_id: string | null;
  balance_after_cents: number;
  memo: string | null;
  created_at: string;
}

export interface Wallet {
  currency: string;
  available_cents: number;
  escrow_cents: number;
  lifetime_net_cents: number;
  recent: LedgerEntry[];
}

interface LedgerPage {
  entries: LedgerEntry[];
  next_cursor: string | null;
}

// Server presets ($10/$25/$50/$100). The server re-validates; this only drives
// which pills render (04-phase-1 · deposits are presets, never client amounts).
export const DEMO_DEPOSIT_PRESETS_CENTS = [1000, 2500, 5000, 10000] as const;

const walletKey = (userId?: string) => ['wallet', userId];

/** Balances + recent ledger. Shared by the Wallet screen and the Play header. */
export function useWallet() {
  const { session } = useAuth();
  return useQuery({
    queryKey: walletKey(session?.user.id),
    enabled: !!session,
    queryFn: async (): Promise<Wallet> => {
      const { data, error } = await api.GET('/api/v1/wallet');
      if (error) throw new Error('Failed to load wallet');
      return data as Wallet;
    },
  });
}

/** Cursor-paginated ledger for the full "Recent" list ("Load more"). */
export function useWalletLedger() {
  const { session } = useAuth();
  return useInfiniteQuery({
    queryKey: ['wallet-ledger', session?.user.id],
    enabled: !!session,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }): Promise<LedgerPage> => {
      const { data, error } = await api.GET('/api/v1/wallet/ledger', {
        params: { query: pageParam ? { cursor: pageParam } : {} },
      });
      if (error) throw new Error('Failed to load ledger');
      return data as LedgerPage;
    },
    getNextPageParam: (last) => last.next_cursor,
  });
}

function useWalletInvalidation() {
  const qc = useQueryClient();
  const { session } = useAuth();
  return () => {
    qc.invalidateQueries({ queryKey: walletKey(session?.user.id) });
    qc.invalidateQueries({ queryKey: ['wallet-ledger', session?.user.id] });
  };
}

export function useDemoDeposit() {
  const invalidate = useWalletInvalidation();
  return useMutation({
    mutationFn: async (amountPresetCents: number): Promise<Wallet> => {
      const { data, error } = await api.POST('/api/v1/wallet/demo-deposit', {
        body: { amount_preset_cents: amountPresetCents },
      });
      if (error) throw new Error('Deposit failed');
      return data as Wallet;
    },
    onSuccess: invalidate,
  });
}

export function useDemoWithdrawal() {
  const invalidate = useWalletInvalidation();
  return useMutation({
    mutationFn: async (amountCents: number): Promise<Wallet> => {
      const { data, error } = await api.POST('/api/v1/wallet/demo-withdrawal', {
        body: { amount_cents: amountCents },
      });
      if (error) throw new Error('Withdrawal failed');
      return data as Wallet;
    },
    onSuccess: invalidate,
  });
}
