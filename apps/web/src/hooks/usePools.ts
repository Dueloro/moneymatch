import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

// Wire types mirror `schemas/pools.py`. Every bar / room bar / payout is
// server-derived; the client only sends metric + difficulty + a preset choice.

export interface DifficultyCard {
  difficulty: string;
  bar: number;
  clear_rate: number;
  est_multiplier_bps: number;
}

export interface PoolMetric {
  metric: string;
  label: string;
  provisional: boolean;
  cards: DifficultyCard[];
}

export interface PoolMarkets {
  game: string;
  linked: boolean;
  entry_presets_cents: number[];
  metrics: PoolMetric[];
}

export interface PoolMember {
  user_id: string;
  username: string | null;
  personal_bar: number;
  status: string;
  payout_cents: number;
  is_you: boolean;
}

export interface PoolView {
  id: string;
  game: string;
  metric: string;
  metric_label: string;
  difficulty: string;
  room_bar: number;
  your_bar: number | null;
  bar_delta: number | null;
  entry_cents: number;
  pot_cents: number;
  prize_cents: number;
  rake_cents: number;
  room_size: number;
  state: string;
  window_starts_at: string;
  window_ends_at: string;
  members: PoolMember[];
  your_payout_cents: number | null;
  resolved_at: string | null;
}

export interface PoolStatus {
  status: 'idle' | 'searching' | 'formed';
  pool: PoolView | null;
  difficulty: string | null;
  metric: string | null;
  waited_seconds: number | null;
}

/** Estimated share-of-pool prize for a given entry: entry × multiplier (display). */
export function estPrize(entryCents: number, multiplierBps: number): number {
  return Math.floor((entryCents * multiplierBps) / 10000);
}

function messageOf(error: unknown, fallback: string): string {
  const msg = (error as { message?: string } | undefined)?.message;
  return typeof msg === 'string' && msg ? msg : fallback;
}

const CS2 = 'cs2.faceit';

export function usePoolMarkets(game: string = CS2) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['pool-markets', game],
    enabled: !!session,
    queryFn: async (): Promise<PoolMarkets> => {
      const { data, error } = await api.GET('/api/v1/pools/markets', {
        params: { query: { game } },
      });
      if (error) throw new Error('Failed to load pool markets');
      return data as PoolMarkets;
    },
  });
}

export function usePoolStatus() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['pool-status', session?.user.id],
    enabled: !!session,
    refetchInterval: 2500,
    queryFn: async (): Promise<PoolStatus> => {
      const { data, error } = await api.GET('/api/v1/pools/queue/status');
      if (error) throw new Error('Failed to load pool status');
      return data as PoolStatus;
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
      return data as PoolStatus;
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
      return data as PoolStatus;
    },
    onSuccess: invalidate,
  });
}
