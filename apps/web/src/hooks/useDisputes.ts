import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '../lib/api';
import { track } from '../lib/telemetry';

export type ContestRefType = 'match' | 'pool' | 'tournament';

export interface ContestVars {
  ref_type: ContestRefType;
  ref_id: string;
  reason: string;
}

function messageOf(error: unknown, fallback: string): string {
  const msg = (error as { message?: string } | undefined)?.message;
  return typeof msg === 'string' && msg ? msg : fallback;
}

/** File a dispute ("contest") against any settled contest — match, pool, or
 * tournament. On success the Activity feed refetches so the card flips to
 * "Contested · under review". */
export function useFileDispute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: ContestVars) => {
      const { data, error } = await api.POST('/api/v1/disputes', { body: vars });
      if (error) throw new Error(messageOf(error, 'Could not submit your contest.'));
      return data;
    },
    onSuccess: (_data, vars) => {
      track('contest_filed', { ref_type: vars.ref_type });
      qc.invalidateQueries({ queryKey: ['activity'] });
    },
  });
}
