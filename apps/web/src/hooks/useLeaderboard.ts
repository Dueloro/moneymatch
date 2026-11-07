import { useQuery } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

export interface LeaderboardRow {
  rank: number;
  user_id: string;
  username: string | null;
  roi_bps: number;
  net_cents: number;
  staked_cents: number;
  contests: number;
  is_you: boolean;
}

export interface YouSummary {
  qualified: boolean;
  contests: number;
  contests_needed: number;
  row: LeaderboardRow | null;
}

export interface LeaderboardResponse {
  rows: LeaderboardRow[];
  you: YouSummary;
  window_days: number;
  min_contests: number;
}

export function useLeaderboard() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['leaderboard'],
    enabled: !!session,
    refetchInterval: 30000,
    queryFn: async (): Promise<LeaderboardResponse> => {
      const { data, error } = await api.GET('/api/v1/leaderboard');
      if (error) throw new Error('Failed to load leaderboard');
      return data as LeaderboardResponse;
    },
  });
}

export function formatRoi(bps: number): string {
  const pct = bps / 100;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}
