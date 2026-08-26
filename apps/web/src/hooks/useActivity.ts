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
  // Matches use PENDING/ACTIVE/…; pools/tournaments use OPEN/LOCKED/SETTLED/CANCELED.
  state: string;
  entry_cents: number;
  // Present for pool/tournament rows; matches build their own title from opponent.
  title: string | null;
  net_cents: number | null;
  opponent_username: string | null;
  your_stat_line: Record<string, unknown> | null;
  opponent_stat_line: Record<string, unknown> | null;
  // Best-effort live in-game view for an in-flight contest, oriented to you.
  // Shape depends on kind/format (pool | tournament | match·chess/stat_race/win_next).
  live: LiveInfo | null;
  // Structured "learn more" payload for the expanded card.
  detail: ActivityDetail | null;
  // The viewer's dispute status on this contest: open | resolved | rejected.
  dispute_status: 'open' | 'resolved' | 'rejected' | null;
  created_at: string;
  resolved_at: string | null;
}

/** Expanded-card detail. Which fields are present depends on `kind`. */
export interface ActivityDetail {
  kind: 'match' | 'pool' | 'tournament';
  game?: string;
  // match
  opponent?: string | null;
  entry_cents?: number;
  prize_cents?: number;
  host_game_id?: string | null;
  map?: string | null;
  mode?: string | null;
  your_stats?: Record<string, number | string> | null;
  opponent_stats?: Record<string, number | string> | null;
  // pool
  difficulty?: string;
  metric_label?: string;
  room_bar?: number;
  personal_bar?: number;
  room_size?: number;
  // tournament
  field_size?: number;
  your_rank?: number | null;
  your_score?: number | null;
}

/** The under-the-card live view. Which fields are present depends on kind/format. */
export interface LiveInfo {
  kind: 'pool' | 'match' | 'tournament';
  format?: 'chess' | 'stat_race' | 'win_next';
  label?: string | null;
  status: string;
  // pool
  target?: number | null;
  current?: number | null;
  cleared?: boolean | null;
  matches?: number;
  // chess
  moves?: number;
  your_color?: string | null;
  turn?: 'you' | 'opp' | null;
  result?: 'you' | 'opp' | 'draw' | null;
  // stat_race / win_next
  you?: number | string | null;
  opp?: number | string | null;
  leader?: 'you' | 'opp' | 'tie' | null;
  // tournament
  score?: number | null;
  rank?: number | null;
  field?: number;
  score_matches?: number;
}

/** The unified activity feed (matches + pools + tournaments). Polls every 10 s. */
export function useActivity() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['activity'],
    enabled: !!session,
    refetchInterval: 10000,
    // Overrides the global `false`. You leave this app to play — the tab you
    // return to is the one holding a result you have not seen, and the interval
    // is paused while backgrounded, so without this the settlement sequence
    // waits on the next tick behind stale data. Cheaper than the poll it is
    // already doing, and it makes Activity itself correct on arrival.
    refetchOnWindowFocus: true,
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
