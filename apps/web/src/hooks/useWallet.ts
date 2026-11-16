import type { components } from '@moneymatch/api-client';
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';
import { messageOf } from '../lib/apiError';
import { formatPoints } from '../lib/format';
import { toast } from '../lib/toast';

export type LedgerEntry = components['schemas']['LedgerEntryResponse'];

export type Wallet = components['schemas']['WalletResponse'];

type LedgerPage = components['schemas']['WalletLedgerPage'];

const walletKey = (userId?: string) => ['wallet', userId];

export function useWallet() {
  const { session } = useAuth();
  return useQuery({
    queryKey: walletKey(session?.user.id),
    enabled: !!session,
    queryFn: async (): Promise<Wallet> => {
      const { data, error } = await api.GET('/api/v1/wallet');
      if (error) throw new Error('Failed to load wallet');
      return data;
    },
  });
}

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
      return data;
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

export function usePlayMoneyDeposit() {
  const invalidate = useWalletInvalidation();
  return useMutation({
    mutationFn: async (amountPresetCents: number): Promise<Wallet> => {
      const { data, error } = await api.POST('/api/v1/wallet/demo-deposit', {
        body: { amount_preset_cents: amountPresetCents },
      });
      if (error) throw new Error(messageOf(error, 'Could not add points'));
      return data;
    },
    onSuccess: (_data, amountPresetCents) => {
      invalidate();
      toast.success(`Added ${formatPoints(amountPresetCents, { long: true })}`);
    },
  });
}
