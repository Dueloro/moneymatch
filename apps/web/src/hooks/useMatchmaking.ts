import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

// Wire types mirror the FastAPI `schemas/play.py` responses. The server owns
// every number; the client only sends intents (market + preset choice + ids).

export interface MarketRow {
  key: string;
  label: string;
  kind: 'win_h2h' | 'win_next' | 'stat_race';
  metric: string | null;
  requires_speed: boolean;
  speeds: string[];
  multiplier_bps: number;
  queue_depth: number;
  provisional: boolean;
  resolution_note: string;
}

export interface MarketsResponse {
  game: string;
  linked: boolean;
  entry_presets_cents: number[];
  markets: MarketRow[];
}

export interface Forecast {
  you_win_prob: number;
  label: string;
}

export interface MatchPlayerView {
  user_id: string;
  username: string | null;
  rating: number | null;
  color: string | null;
  confirmed: boolean;
  payout_cents: number;
  stat_line: Record<string, unknown> | null;
  is_you: boolean;
}

export interface MatchView {
  id: string;
  game: string;
  market: string;
  market_label: string;
  kind: string;
  speed: string | null;
  entry_cents: number;
  pot_cents: number;
  prize_cents: number;
  rake_cents: number;
  multiplier_bps: number;
  state: 'PENDING' | 'ACTIVE' | 'AWAITING_RESULT' | 'SETTLED' | 'PUSHED' | 'CANCELED';
  brokered: boolean;
  host_game_id: string | null;
  matched_at: string | null;
  window_ends_at: string | null;
  players: MatchPlayerView[];
  you_confirmed: boolean;
  your_play_url: string | null;
  forecast: Forecast | null;
}

export interface QueueStatus {
  status: 'idle' | 'searching' | 'matched';
  match: MatchView | null;
  waited_seconds: number | null;
  tolerance_stage: number | null;
  can_cancel: boolean;
}

export interface WaitingRow {
  ticket_id: string;
  game: string;
  market: string;
  market_label: string;
  speed: string | null;
  entry_cents: number;
  username: string | null;
  rating: number | null;
  waited_seconds: number;
}

/** Derived "You'd win" figure: entry × 2 × (1 − rake). Exact integer cents. */
export function prizeForEntry(entryCents: number, multiplierBps: number): number {
  return Math.floor((entryCents * multiplierBps) / 10000);
}

function messageOf(error: unknown, fallback: string): string {
  const msg = (error as { message?: string } | undefined)?.message;
  return typeof msg === 'string' && msg ? msg : fallback;
}

// --- reads ---------------------------------------------------------------- //

export function useMarkets(game: string | undefined) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['markets', game],
    enabled: !!session && !!game,
    queryFn: async (): Promise<MarketsResponse> => {
      const { data, error } = await api.GET('/api/v1/play/markets', {
        params: { query: { game: game! } },
      });
      if (error) throw new Error('Failed to load markets');
      return data as MarketsResponse;
    },
  });
}

/** The viewer's live queue standing. Polls every 2 s (design: queue status 2 s). */
export function useQueueStatus() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['queue-status', session?.user.id],
    enabled: !!session,
    refetchInterval: 2000,
    queryFn: async (): Promise<QueueStatus> => {
      const { data, error } = await api.GET('/api/v1/play/queue/status');
      if (error) throw new Error('Failed to load queue status');
      return data as QueueStatus;
    },
  });
}

export function useWaiting(game: string | undefined) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['waiting', game],
    enabled: !!session,
    refetchInterval: 5000,
    queryFn: async (): Promise<{ waiting: WaitingRow[] }> => {
      const { data, error } = await api.GET('/api/v1/play/waiting', {
        params: { query: game ? { game } : {} },
      });
      if (error) throw new Error('Failed to load waiting list');
      return data as { waiting: WaitingRow[] };
    },
  });
}

// --- mutations ------------------------------------------------------------ //

function useQueueInvalidation() {
  const qc = useQueryClient();
  const { session } = useAuth();
  return () => {
    qc.invalidateQueries({ queryKey: ['queue-status', session?.user.id] });
    qc.invalidateQueries({ queryKey: ['waiting'] });
    qc.invalidateQueries({ queryKey: ['wallet', session?.user.id] });
    qc.invalidateQueries({ queryKey: ['activity'] });
  };
}

export function useJoinQueue() {
  const invalidate = useQueueInvalidation();
  return useMutation({
    mutationFn: async (vars: {
      game: string;
      market: string;
      speed?: string;
      entry_preset_cents: number;
    }): Promise<QueueStatus> => {
      const { data, error } = await api.POST('/api/v1/play/queue', { body: vars });
      if (error) throw new Error(messageOf(error, 'Could not join the queue.'));
      return data as QueueStatus;
    },
    onSuccess: invalidate,
  });
}

export function useLeaveQueue() {
  const invalidate = useQueueInvalidation();
  return useMutation({
    mutationFn: async (): Promise<QueueStatus> => {
      const { data, error } = await api.DELETE('/api/v1/play/queue');
      if (error) throw new Error('Could not leave the queue.');
      return data as QueueStatus;
    },
    onSuccess: invalidate,
  });
}

export function useTakeWaiting() {
  const invalidate = useQueueInvalidation();
  return useMutation({
    mutationFn: async (ticketId: string): Promise<MatchView> => {
      const { data, error } = await api.POST('/api/v1/play/waiting/{ticket_id}/match', {
        params: { path: { ticket_id: ticketId } },
      });
      if (error) throw new Error(messageOf(error, 'Could not take that slot.'));
      return data as MatchView;
    },
    onSuccess: invalidate,
  });
}

export function useConfirmMatch() {
  const invalidate = useQueueInvalidation();
  return useMutation({
    mutationFn: async (matchId: string): Promise<MatchView> => {
      const { data, error } = await api.POST(
        '/api/v1/play/matches/{match_id}/confirm',
        {
          params: { path: { match_id: matchId } },
        },
      );
      if (error) throw new Error(messageOf(error, 'Could not confirm.'));
      return data as MatchView;
    },
    onSuccess: invalidate,
  });
}

export function useDeclineMatch() {
  const invalidate = useQueueInvalidation();
  return useMutation({
    mutationFn: async (matchId: string): Promise<MatchView> => {
      const { data, error } = await api.POST(
        '/api/v1/play/matches/{match_id}/decline',
        {
          params: { path: { match_id: matchId } },
        },
      );
      if (error) throw new Error(messageOf(error, 'Could not decline.'));
      return data as MatchView;
    },
    onSuccess: invalidate,
  });
}
