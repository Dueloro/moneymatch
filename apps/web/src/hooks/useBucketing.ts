import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

// Mirrors schemas/bucketing.py. The server owns every number (bucket, bar, cap);
// the client only picks a stake within the returned cap.

export interface BucketMarketCard {
  game: string;
  mode: string;
  metric: string;
  label: string;
  placed: boolean;
  bucket: number | null;
  bar: number | null;
  stake_cap_cents: number | null;
  provisional: boolean;
  multiplier_bps: number;
}

export interface BucketMarketsResponse {
  enabled: boolean;
  markets: BucketMarketCard[];
}

export interface BucketContestStatus {
  contest_id: string;
  game: string;
  mode: string;
  metric: string;
  bucket: number;
  status: string;
  stake_cents: number;
  bar: number | null;
  result_value: number | null;
  cleared: boolean | null;
  payout_cents: number;
  room_id: string | null;
}

export function useBucketMarkets() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['bucketing-markets', session?.user.id],
    enabled: !!session,
    queryFn: async (): Promise<BucketMarketsResponse> => {
      const { data, error } = await api.GET('/api/v1/bucketing/markets');
      if (error) throw new Error('Failed to load bucketing markets');
      return data as BucketMarketsResponse;
    },
  });
}

export function usePlaceBucketWager() {
  const { session } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      game: string;
      mode: string;
      metric: string;
      stake_cents: number;
    }): Promise<BucketContestStatus> => {
      const { data, error } = await api.POST('/api/v1/bucketing/wagers', {
        body: vars,
      });
      if (error) {
        const code = (error as { code?: string }).code;
        throw new Error(code ?? 'Could not place the wager');
      }
      return data as BucketContestStatus;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bucketing-markets', session?.user.id] });
      qc.invalidateQueries({ queryKey: ['wallet', session?.user.id] });
    },
  });
}
