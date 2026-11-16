import type { components } from '@moneymatch/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';
import { messageOf } from '../lib/apiError';
import { CHESS } from '../lib/games';

export type TournamentMetric = components['schemas']['TournamentMetric'];

export type TournamentMarkets = components['schemas']['TournamentMarketsResponse'];

export type StandingRow = components['schemas']['StandingRow'];

export type TournamentView = components['schemas']['TournamentView'];

export type TournamentStatus = components['schemas']['TournamentStatusResponse'];

export function useTournamentMarkets(game: string = CHESS) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['tournament-markets', game],
    enabled: !!session,
    queryFn: async (): Promise<TournamentMarkets> => {
      const { data, error } = await api.GET('/api/v1/tournaments/markets', {
        params: { query: { game } },
      });
      if (error) throw new Error('Failed to load tournament markets');
      return data;
    },
  });
}

export function useTournamentStatus() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['tournament-status', session?.user.id],
    enabled: !!session,
    refetchInterval: (query) =>
      query.state.data?.status === 'searching' ? 2500 : 10_000,
    queryFn: async (): Promise<TournamentStatus> => {
      const { data, error } = await api.GET('/api/v1/tournaments/queue/status');
      if (error) throw new Error('Failed to load tournament status');
      return data;
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

export function useTournament(tournamentId: string | null) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['tournament', tournamentId],
    enabled: !!session && !!tournamentId,
    staleTime: 30_000,
    queryFn: async (): Promise<TournamentView> => {
      const { data, error } = await api.GET('/api/v1/tournaments/{tournament_id}', {
        params: { path: { tournament_id: tournamentId as string } },
      });
      if (error) throw new Error('Failed to load the tournament');
      return data;
    },
  });
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
      return data;
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
      return data;
    },
    onSuccess: invalidate,
  });
}
