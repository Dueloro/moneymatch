import { useQuery } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

export interface ActivityItem {
  type: 'match' | 'pool' | 'tournament';
  id: string;
  game: string;
  market: string;
  market_label: string;
  kind: string;
  // Matches use PENDING/ACTIVE/…; pools/tournaments use
  // OPEN/LOCKED/SETTLED/CANCELED.
  state: string;
  entry_cents: number;
  title: string | null;
  net_cents: number | null;
  opponent_username: string | null;
  your_stat_line: Record<string, unknown> | null;
  opponent_stat_line: Record<string, unknown> | null;
  live: LiveInfo | null;
  detail: ActivityDetail | null;
  dispute_status: 'open' | 'resolved' | 'rejected' | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ActivityDetail {
  kind: 'match' | 'pool' | 'tournament';
  game?: string;
  opponent?: string | null;
  entry_cents?: number;
  prize_cents?: number;
  host_game_id?: string | null;
  your_stats?: Record<string, number | string> | null;
  opponent_stats?: Record<string, number | string> | null;
  difficulty?: string;
  metric_label?: string;
  room_bar?: number;
  personal_bar?: number;
  room_size?: number;
  field_size?: number;
  your_rank?: number | null;
  your_score?: number | null;
}

export interface LiveInfo {
  kind: 'pool' | 'match' | 'tournament';
  format?: 'chess';
  label?: string | null;
  status: string;
  target?: number | null;
  current?: number | null;
  cleared?: boolean | null;
  matches?: number;
  moves?: number;
  your_color?: string | null;
  turn?: 'you' | 'opp' | null;
  result?: 'you' | 'opp' | 'draw' | null;
  score?: number | null;
  rank?: number | null;
  field?: number;
}

export function useActivity() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['activity'],
    enabled: !!session,
    refetchInterval: 10000,
    refetchOnWindowFocus: true,
    queryFn: async (): Promise<{ items: ActivityItem[] }> => {
      const { data, error } = await api.GET('/api/v1/activity');
      if (error) throw new Error('Failed to load activity');
      return data as { items: ActivityItem[] };
    },
  });
}

export function statValue(line: Record<string, unknown> | null): number | null {
  if (!line) return null;
  for (const [key, value] of Object.entries(line)) {
    if (key === 'game_id') continue;
    if (typeof value === 'number') return value;
  }
  return null;
}
