import { useMutation, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { env } from '../lib/env';

/**
 * Reset the shared demo account to its fresh-login state (demo user only). The
 * server refunds any in-flight contests, restores the starting balance, and
 * re-applies the seed; here we blow away every cached query so the whole app
 * re-reads the reset state.
 */
export function useResetDemo() {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<void> => {
      const res = await fetch(`${env.apiBaseUrl}/api/v1/demo/reset`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session?.access_token ?? ''}` },
      });
      if (!res.ok) throw new Error('Could not reset the demo.');
    },
    onSuccess: () => queryClient.invalidateQueries(),
  });
}
