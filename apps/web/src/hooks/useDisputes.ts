import type { components } from '@moneymatch/api-client';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '../lib/api';
import { messageOf } from '../lib/apiError';
import { track } from '../lib/telemetry';

export type ContestRefType = 'match' | 'pool' | 'tournament';

export type ContestVars = components['schemas']['ContestRequest'];

export function useFileDispute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: ContestVars) => {
      const { data, error } = await api.POST('/api/v1/disputes', { body: vars });
      if (error) throw new Error(messageOf(error, 'Could not send your report.'));
      return data;
    },
    onSuccess: (_data, vars) => {
      track('contest_filed', { ref_type: vars.ref_type });
      qc.invalidateQueries({ queryKey: ['activity'] });
    },
  });
}
