import { useQuery } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

export interface ActivityItem {
  type: 'match';
  id: string;
  game: string;
  market: string;
  market_label: string;
  kind: string;
  state: 'PENDING' | 'ACTIVE' | 'AWAITING_RESULT' | 'SETTLED' | 'PUSHED' | 'CANCELED';
  entry_cents: number;
  net_cents: number | null;
  opponent_username: string | null;
  your_stat_line: Record<string, unknown> | null;
  opponent_stat_line: Record<string, unknown> | null;
  created_at: string;
  resolved_at: string | null;
}

/** The unified activity feed (H2H now). Polls every 10 s (design: activity 10 s). */
export function useActivity() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['activity'],
    enabled: !!session,
    refetchInterval: 10000,
    queryFn: async (): Promise<{ items: ActivityItem[] }> => {
      const { data, error } = await api.GET('/api/v1/activity');
      if (error) throw new Error('Failed to load activity');
      return data as { items: ActivityItem[] };
    },
  });
}

/** The graded stat value from a stat-race `stat_line` (skips the `game_id` field). */
export function statValue(line: Record<string, unknown> | null): number | null {
  if (!line) return null;
  for (const [key, value] of Object.entries(line)) {
    if (key === 'game_id') continue;
    if (typeof value === 'number') return value;
  }
  return null;
}
