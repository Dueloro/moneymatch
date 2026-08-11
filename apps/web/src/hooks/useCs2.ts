import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

/**
 * CS2 over Steam: sign in, then submit the share code that settles a wager.
 *
 * A share code is the only artifact a player can copy out of CS2. There is no
 * public per-match stats API, so pasting one is how a real match enters the
 * system: the server resolves it through the Game Coordinator, stores the
 * scoreboard, and every in-flight wager whose window contains that match grades
 * against it.
 */

export interface ShareCodePlayer {
  steam_id: string;
  kills: number;
  deaths: number;
  headshots: number;
  is_you: boolean;
}

export interface SubmittedMatch {
  share_code: string;
  match_time: string;
  map_name: string | null;
  rounds: number;
  score: string;
  demo_expired: boolean;
  your_metrics: Record<string, number>;
  players: ShareCodePlayer[];
}

/** Where to send the user to sign in through Steam. */
export function useSteamLoginUrl() {
  return useQuery({
    queryKey: ['steam-login-url'],
    staleTime: Infinity,
    queryFn: async (): Promise<string> => {
      const { data, error } = await api.GET('/api/v1/cs2/steam/login-url');
      if (error) throw new Error('Could not start Steam sign-in');
      return (data as { url: string }).url;
    },
  });
}

/**
 * Whether the Game Coordinator sidecar is reachable.
 *
 * Worth surfacing rather than hiding: if it is down, pasting a code cannot
 * work, and a player deserves to know that before they try rather than after.
 */
export function useGcHealth() {
  return useQuery({
    queryKey: ['gc-health'],
    refetchInterval: 30_000,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/cs2/health');
      if (error) throw new Error('Could not read match service health');
      return data as { ready: boolean; queue_depth: number };
    },
  });
}

export function useSubmitShareCode() {
  const queryClient = useQueryClient();
  const { session } = useAuth();
  return useMutation({
    mutationFn: async (shareCode: string): Promise<SubmittedMatch> => {
      const { data, error, response } = await api.POST('/api/v1/cs2/sharecode', {
        body: { share_code: shareCode },
      });
      if (error || !data) {
        // The server's rejections are the useful part: "you were not in that
        // match", "that match was played before you joined". Surfacing a
        // generic failure here would throw away the only thing the player can
        // act on.
        const detail = error as { message?: string; code?: string } | undefined;
        throw new Error(
          detail?.message ??
            (response?.status === 503
              ? 'The CS2 match service is unavailable. Try again in a moment.'
              : 'Could not submit that share code.'),
        );
      }
      return data as SubmittedMatch;
    },
    onSuccess: () => {
      // A submitted match can settle a contest, so anything showing money or
      // contest state is now stale.
      for (const key of ['pool-status', 'tournament-status', 'activity', 'wallet']) {
        queryClient.invalidateQueries({ queryKey: [key, session?.user.id] });
        queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}
