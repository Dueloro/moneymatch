import { useQuery } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

export interface StreakRow {
  game: string;
  mode: string;
  streak: number;
  best_streak: number;
}

/**
 * The player's win streaks per (game, mode). A streak lifts *who you're matched
 * with* a rung per consecutive win and resets on a loss — matchmaking only, never
 * what you wager.
 */
export function useStreaks() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['play-streaks', session?.user.id],
    enabled: !!session,
    queryFn: async (): Promise<StreakRow[]> => {
      const { data, error } = await api.GET('/api/v1/play/streaks');
      if (error) throw new Error('Failed to load streaks');
      return ((data as { streaks?: StreakRow[] }).streaks ?? []) as StreakRow[];
    },
  });
}

/** The best current streak for a game (max across its modes), or 0. */
export function useGameStreak(game: string | undefined): number {
  const { data } = useStreaks();
  if (!game || !data) return 0;
  return data
    .filter((s) => s.game === game)
    .reduce((best, s) => Math.max(best, s.streak), 0);
}
