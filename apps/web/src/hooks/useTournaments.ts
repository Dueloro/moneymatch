import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

// Wire types mirror `schemas/tournaments.py`. Scores, ranks, and payouts are all
// server-computed; the client only picks a metric + a preset entry.

export interface TournamentMetric {
  metric: string;
  label: string;
  provisional: boolean;
}

export interface TournamentMarkets {
  game: string;
  linked: boolean;
  entry_presets_cents: number[];
  prize_split: number[];
  field_size: number;
  score_matches: number;
  metrics: TournamentMetric[];
}

export interface StandingRow {
  user_id: string;
  username: string | null;
  score: number | null;
  matches: number;
  rank: number | null;
  is_you: boolean;
  payout_cents: number;
}

export interface TournamentView {
  id: string;
  game: string;
  metric: string;
  metric_label: string;
  entry_cents: number;
  pot_cents: number;
  prize_cents: number;
  rake_cents: number;
  prize_split: number[];
  field_size: number;
  score_matches: number;
  state: string;
  window_starts_at: string;
  window_ends_at: string;
  field_mu_low: number | null;
  field_mu_high: number | null;
  standings: StandingRow[];
  your_rank: number | null;
  your_payout_cents: number | null;
  resolved_at: string | null;
}

export interface TournamentStatus {
  status: 'idle' | 'searching' | 'formed';
  tournament: TournamentView | null;
  metric: string | null;
  waited_seconds: number | null;
}

function messageOf(error: unknown, fallback: string): string {
  const msg = (error as { message?: string } | undefined)?.message;
  return typeof msg === 'string' && msg ? msg : fallback;
}

const CS2 = 'cs2.faceit';

export function useTournamentMarkets(game: string = CS2) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['tournament-markets', game],
    enabled: !!session,
    queryFn: async (): Promise<TournamentMarkets> => {
      const { data, error } = await api.GET('/api/v1/tournaments/markets', {
        params: { query: { game } },
      });
      if (error) throw new Error('Failed to load tournament markets');
      return data as TournamentMarkets;
    },
  });
}

export function useTournamentStatus() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['tournament-status', session?.user.id],
    enabled: !!session,
    refetchInterval: 5000,
    queryFn: async (): Promise<TournamentStatus> => {
      const { data, error } = await api.GET('/api/v1/tournaments/queue/status');
      if (error) throw new Error('Failed to load tournament status');
      return data as TournamentStatus;
    },
  });
}

function useInvalidate() {
  const qc = useQueryClient();
  const { session } = useAuth();
  return () => {
    qc.invalidateQueries({ queryKey: ['tournament-status', session?.user.id] });
    qc.invalidateQueries({ queryKey: ['wallet', session?.user.id] });
    qc.invalidateQueries({ queryKey: ['activity'] });
  };
}

export function useEnterTournament() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (vars: {
      game: string;
      metric: string;
      entry_preset_cents: number;
    }): Promise<TournamentStatus> => {
      const { data, error } = await api.POST('/api/v1/tournaments/queue', {
        body: vars,
      });
      if (error) throw new Error(messageOf(error, 'Could not enter the tournament.'));
      return data as TournamentStatus;
    },
    onSuccess: invalidate,
  });
}

export function useLeaveTournament() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (): Promise<TournamentStatus> => {
      const { data, error } = await api.DELETE('/api/v1/tournaments/queue');
      if (error) throw new Error('Could not leave the tournament queue.');
      return data as TournamentStatus;
    },
    onSuccess: invalidate,
  });
}
