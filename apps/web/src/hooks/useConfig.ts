import type { components } from '@moneymatch/api-client';
import { useQuery } from '@tanstack/react-query';

import { api } from '../lib/api';

export type ClientConfig = components['schemas']['ClientConfig'];

/** The server's excluded states, fee and top-up presets. The app keeps no copies. */
export function useConfig() {
  return useQuery({
    queryKey: ['config'],
    staleTime: Infinity,
    queryFn: async (): Promise<ClientConfig> => {
      const { data, error } = await api.GET('/api/v1/config');
      if (error || !data) throw new Error('Failed to load config');
      return data;
    },
  });
}

export function useIsExcludedState(code: string | null | undefined): boolean {
  const { data } = useConfig();
  return !!code && !!data?.excluded_states.includes(code);
}
