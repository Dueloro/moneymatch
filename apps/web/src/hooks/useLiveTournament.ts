import { useMutation, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { env } from '../lib/env';

/**
 * Demo-only: start (or advance) a self-driving live tournament.
 *
 * `start` creates a ~10-minute chess tournament, enters the demo user plus
 * competitive bots, and injects stats fetched from the real Lichess API that
 * keep changing over the window (so standings move like people are playing). The
 * existing Tournament page renders it via the queue-status banner. `tick`
 * fast-forwards it by injecting the next round of games now, so a tester doesn't
 * have to wait for the timer.
 *
 * Both are behind `demo_simulate_enabled` on the server and only work for the
 * shared demo account; a real signup gets a 403/404.
 */
export function useStartLiveTournament() {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<{ tournament_id: string; message: string }> => {
      const res = await fetch(`${env.apiBaseUrl}/api/v1/demo/live_tournament`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session?.access_token ?? ''}` },
      });
      if (!res.ok) {
        throw new Error('Could not start the live tournament (demo only).');
      }
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries(),
  });
}

export function useTickLiveTournament() {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<{ advanced: number }> => {
      const res = await fetch(`${env.apiBaseUrl}/api/v1/demo/live_tournament/tick`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session?.access_token ?? ''}` },
      });
      if (!res.ok) throw new Error('Could not advance the live tournament.');
      return res.json();
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['tournament-status'] }),
  });
}
