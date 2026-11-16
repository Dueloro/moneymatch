import type { components } from '@moneymatch/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';
import { messageOf } from '../lib/apiError';
import { CHESS } from '../lib/games';

export type DifficultyCard = components['schemas']['DifficultyCard'];

export type PoolMetric = components['schemas']['PoolMetric'];

export type PoolMarkets = components['schemas']['PoolMarketsResponse'];

export type PoolMember = components['schemas']['PoolMemberView'];

export type PoolView = components['schemas']['PoolView'];

export type PoolStatus = components['schemas']['PoolStatusResponse'];

export function estPrize(entryCents: number, multiplierBps: number): number {
  return Math.floor((entryCents * multiplierBps) / 10000);
}

export function usePoolMarkets(game: string = CHESS) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['pool-markets', game],
    enabled: !!session,
    queryFn: async (): Promise<PoolMarkets> => {
      const { data, error } = await api.GET('/api/v1/pools/markets', {
        params: { query: { game } },
      });
      if (error) throw new Error('Failed to load pool markets');
      return data;
    },
  });
}

export function usePoolStatus() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['pool-status', session?.user.id],
    enabled: !!session,
    refetchInterval: (query) =>
      query.state.data?.status === 'searching' ? 2500 : 10_000,
    queryFn: async (): Promise<PoolStatus> => {
      const { data, error } = await api.GET('/api/v1/pools/queue/status');
      if (error) throw new Error('Failed to load pool status');
      return data;
    },
  });
}

export function usePool(poolId: string | null) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['pool', poolId],
    enabled: !!session && !!poolId,
    staleTime: 30_000,
    queryFn: async (): Promise<PoolView> => {
      const { data, error } = await api.GET('/api/v1/pools/{pool_id}', {
        params: { path: { pool_id: poolId as string } },
      });
      if (error) throw new Error('Failed to load the room');
      return data;
    },
  });
}

function useInvalidate() {
  const qc = useQueryClient();
  const { session } = useAuth();
  return () => {
    qc.invalidateQueries({ queryKey: ['pool-status', session?.user.id] });
    qc.invalidateQueries({ queryKey: ['wallet', session?.user.id] });
    qc.invalidateQueries({ queryKey: ['activity'] });
  };
}

export function useEnterPool() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (vars: {
      game: string;
      metric: string;
      difficulty: string;
      entry_preset_cents: number;
    }): Promise<PoolStatus> => {
      const { data, error } = await api.POST('/api/v1/pools/queue', { body: vars });
      if (error) throw new Error(messageOf(error, 'Could not enter the pool.'));
      return data;
    },
    onSuccess: invalidate,
  });
}

export function useLeavePool() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (): Promise<PoolStatus> => {
      const { data, error } = await api.DELETE('/api/v1/pools/queue');
      if (error) throw new Error('Could not leave the pool queue.');
      return data;
    },
    onSuccess: invalidate,
  });
}
