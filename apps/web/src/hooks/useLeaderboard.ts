import type { components } from '@moneymatch/api-client';
import { useQuery } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

export type LeaderboardRow = components['schemas']['LeaderboardRowView'];

export type YouSummary = components['schemas']['YouSummaryView'];

export type LeaderboardResponse = components['schemas']['LeaderboardResponse'];

export function useLeaderboard() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['leaderboard'],
    enabled: !!session,
    refetchInterval: 30000,
    queryFn: async (): Promise<LeaderboardResponse> => {
      const { data, error } = await api.GET('/api/v1/leaderboard');
      if (error) throw new Error('Failed to load leaderboard');
      return data;
    },
  });
}

export function formatRoi(bps: number): string {
  const pct = bps / 100;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}
