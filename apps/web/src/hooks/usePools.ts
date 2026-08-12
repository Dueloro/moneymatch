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
  /** What they scored on the graded match. Null while the window is open. */
  result_value?: number | null;
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
  // Live result while the window runs: did your played match clear the room bar,
  // and the value it hit. Null until you've played (or on a host outage).
  your_cleared: boolean | null;
  your_current: number | null;
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

const CS2 = 'cs2.steam';

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
    // The rail mounts this app-wide, so only poll hard while a room is actually
    // forming. Idle and formed both change off the back of something that
    // already invalidates the key (a join, a leave, a settlement).
    refetchInterval: (query) =>
      query.state.data?.status === 'searching' ? 2500 : 10_000,
    queryFn: async (): Promise<PoolStatus> => {
      const { data, error } = await api.GET('/api/v1/pools/queue/status');
      if (error) throw new Error('Failed to load pool status');
      return data as PoolStatus;
    },
  });
}

/**
 * One settled or in-flight room, by id.
 *
 * Used by the notification feed, where a row is opened to see who is in the
 * room and how it finished. `enabled` is what makes it lazy: the row only
 * mounts this when the card is expanded, so the feed costs nothing to render.
 */
export function usePool(poolId: string | null) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['pool', poolId],
    enabled: !!session && !!poolId,
    // A room's roster and result do not change once settled, and while it is
    // live the rail is already polling status.
    staleTime: 30_000,
    queryFn: async (): Promise<PoolView> => {
      const { data, error } = await api.GET('/api/v1/pools/{pool_id}', {
        params: { path: { pool_id: poolId as string } },
      });
      if (error) throw new Error('Failed to load the room');
      return data as PoolView;
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
