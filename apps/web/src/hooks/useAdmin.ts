import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../lib/api';

// Dense operator types (mirrors schemas/admin.py). The admin surface is plain and
// boring by design (09-phase-6 · deliverable 2) — not the consumer design system.

export interface FlagItem {
  key: string;
  enabled: boolean;
  payload: Record<string, unknown>;
}

export interface AdminUserSummary {
  id: string;
  username: string | null;
  email: string | null;
  friend_code: string;
  role: string;
  status: string;
  residence_state: string | null;
  member_since: string;
  available_cents: number;
  escrow_cents: number;
}

export interface AdminContestListItem {
  ref_type: string;
  ref_id: string;
  game: string;
  market: string;
  state: string;
  entry_cents: number;
  pot_cents: number;
  participants: number;
  created_at: string;
  resolved_at: string | null;
}

// --- Flags ----------------------------------------------------------------- //

export function useAdminFlags() {
  return useQuery({
    queryKey: ['admin', 'flags'],
    queryFn: async (): Promise<FlagItem[]> => {
      const { data, error } = await api.GET('/api/v1/admin/flags');
      if (error) throw new Error('Failed to load flags');
      return (data as { flags: FlagItem[] }).flags;
    },
  });
}

export function useUpdateFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      key: string;
      enabled?: boolean;
      payload?: Record<string, unknown>;
    }): Promise<void> => {
      const { error } = await api.PUT('/api/v1/admin/flags/{key}', {
        params: { path: { key: input.key } },
        body: { enabled: input.enabled ?? null, payload: input.payload ?? null },
      });
      if (error) throw new Error('Failed to update flag');
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'flags'] }),
  });
}

// --- Users ----------------------------------------------------------------- //

export function useAdminUsers(q: string) {
  return useQuery({
    queryKey: ['admin', 'users', q],
    queryFn: async (): Promise<AdminUserSummary[]> => {
      const { data, error } = await api.GET('/api/v1/admin/users', {
        params: { query: q ? { q } : {} },
      });
      if (error) throw new Error('Failed to search users');
      return (data as { users: AdminUserSummary[] }).users;
    },
  });
}

export function useAdminUser(userId: string | null) {
  return useQuery({
    queryKey: ['admin', 'user', userId],
    enabled: !!userId,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/admin/users/{user_id}', {
        params: { path: { user_id: userId! } },
      });
      if (error) throw new Error('Failed to load user');
      return data as Record<string, unknown>;
    },
  });
}

function useUserRefresh(userId: string | null) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ['admin', 'user', userId] });
    qc.invalidateQueries({ queryKey: ['admin', 'users'] });
  };
}

export function useFreezeUser(userId: string | null) {
  const refresh = useUserRefresh(userId);
  return useMutation({
    mutationFn: async (freeze: boolean): Promise<void> => {
      const params = { params: { path: { user_id: userId! } } };
      const { error } = freeze
        ? await api.POST('/api/v1/admin/users/{user_id}/freeze', params)
        : await api.POST('/api/v1/admin/users/{user_id}/unfreeze', params);
      if (error) throw new Error('Action failed');
    },
    onSuccess: refresh,
  });
}

export function useAdjustUser(userId: string | null) {
  const refresh = useUserRefresh(userId);
  return useMutation({
    mutationFn: async (input: {
      amount_cents: number;
      reason: string;
    }): Promise<void> => {
      const { error } = await api.POST('/api/v1/admin/users/{user_id}/adjust', {
        params: { path: { user_id: userId! } },
        body: input,
      });
      if (error) throw new Error('Adjustment failed');
    },
    onSuccess: refresh,
  });
}

// --- Contests -------------------------------------------------------------- //

export function useAdminContests(filters: { state?: string; game?: string }) {
  return useQuery({
    queryKey: ['admin', 'contests', filters],
    queryFn: async (): Promise<AdminContestListItem[]> => {
      const { data, error } = await api.GET('/api/v1/admin/contests', {
        params: { query: filters },
      });
      if (error) throw new Error('Failed to load contests');
      return (data as { contests: AdminContestListItem[] }).contests;
    },
  });
}

export function useContestDetail(refType: string | null, refId: string | null) {
  return useQuery({
    queryKey: ['admin', 'contest', refType, refId],
    enabled: !!refType && !!refId,
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/api/v1/admin/contests/{ref_type}/{ref_id}',
        { params: { path: { ref_type: refType!, ref_id: refId! } } },
      );
      if (error) throw new Error('Failed to load contest');
      return data as Record<string, unknown>;
    },
  });
}

export function useResettleMatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (matchId: string): Promise<void> => {
      const { error } = await api.POST('/api/v1/admin/matches/{match_id}/resettle', {
        params: { path: { match_id: matchId } },
      });
      if (error) throw new Error('Resettle failed');
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin'] }),
  });
}

export function useVoidMatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { matchId: string; reason: string }): Promise<void> => {
      const { error } = await api.POST('/api/v1/admin/matches/{match_id}/void', {
        params: { path: { match_id: input.matchId } },
        body: { reason: input.reason },
      });
      if (error) throw new Error('Void failed');
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin'] }),
  });
}

export function useVoidTournament() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      tournamentId: string;
      reason: string;
    }): Promise<void> => {
      const { error } = await api.POST(
        '/api/v1/admin/tournaments/{tournament_id}/void',
        {
          params: { path: { tournament_id: input.tournamentId } },
          body: { reason: input.reason },
        },
      );
      if (error) throw new Error('Void failed');
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin'] }),
  });
}

// --- Stored match log (background ingestion) ------------------------------ //

export interface AdminGameMatch {
  id: string;
  user_id: string;
  username: string | null;
  host_username: string | null;
  game: string;
  host_account_id: string;
  host_match_id: string;
  started_at: string;
  ended_at: string | null;
  mode: string | null;
  rated: boolean;
  eligible: boolean;
  result: string | null;
  moves: number;
  metrics: Record<string, number>;
  detail: Record<string, unknown>;
  fetched_at: string;
  account_last_polled_at: string | null;
}

export function useAdminGameMatches(filters: { player?: string; game?: string }) {
  return useQuery({
    queryKey: ['admin', 'game-matches', filters],
    refetchInterval: 30_000,
    queryFn: async (): Promise<AdminGameMatch[]> => {
      const { data, error } = await api.GET('/api/v1/admin/game-matches', {
        params: {
          query: {
            player: filters.player || undefined,
            game: filters.game || undefined,
            limit: 200,
          },
        },
      });
      if (error) throw new Error('Failed to load stored matches');
      return (data as { matches: AdminGameMatch[] }).matches;
    },
  });
}

// --- Queue / Reconciliation / Risk ---------------------------------------- //

export function useAdminQueue() {
  return useQuery({
    queryKey: ['admin', 'queue'],
    refetchInterval: 5000,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/admin/queue');
      if (error) throw new Error('Failed to load queue');
      return data as Record<string, unknown>;
    },
  });
}

export function useReconciliation() {
  return useQuery({
    queryKey: ['admin', 'reconciliation'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/admin/reconciliation');
      if (error) throw new Error('Failed to run reconciliation');
      return data as Record<string, unknown>;
    },
  });
}

export function useRisk() {
  return useQuery({
    queryKey: ['admin', 'risk'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/admin/risk');
      if (error) throw new Error('Failed to load risk');
      return data as Record<string, unknown>;
    },
  });
}

export function useClearFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (flagId: string): Promise<void> => {
      const { error } = await api.POST('/api/v1/admin/risk/flags/{flag_id}/clear', {
        params: { path: { flag_id: flagId } },
      });
      if (error) throw new Error('Clear failed');
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'risk'] }),
  });
}

// --- Disputes -------------------------------------------------------------- //

export interface AdminDispute {
  id: string;
  ref_type: string; // match | pool | tournament
  ref_id: string;
  user_id: string;
  reason: string;
  status: string;
  admin_note: string | null;
  created_at: string;
  resolved_at: string | null;
}

/** Open, user-filed contest disputes awaiting admin review. */
export function useAdminDisputes() {
  return useQuery({
    queryKey: ['admin', 'disputes'],
    refetchInterval: 10000,
    queryFn: async (): Promise<AdminDispute[]> => {
      const { data, error } = await api.GET('/api/v1/admin/disputes');
      if (error) throw new Error('Failed to load disputes');
      return data as AdminDispute[];
    },
  });
}

export function useResolveDispute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      dispute_id: string;
      status: 'resolved' | 'rejected';
      note?: string;
    }): Promise<void> => {
      const { error } = await api.POST('/api/v1/admin/disputes/{dispute_id}/resolve', {
        params: { path: { dispute_id: input.dispute_id } },
        body: { status: input.status, note: input.note ?? null },
      });
      if (error) throw new Error('Resolve failed');
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'disputes'] }),
  });
}

// --- Tournament settlement log (permanent, written at settlement) ---------- //

export interface AdminTournamentLogMatch {
  host_match_id: string;
  game_match_id: string | null;
  started_at: string;
  ended_at: string | null;
  fetched_at: string | null;
  mode: string | null;
  result: string | null;
  reason: string;
  reason_text: string;
  counted: boolean;
  value: number | null;
  metrics: Record<string, number>;
  recorded_at: string;
}

export interface AdminTournamentLogEntrant {
  entry_id: string;
  user_id: string;
  username: string | null;
  host_account_id: string;
  entered_at: string;
  score: number | null;
  matches_counted: number;
  rank: number | null;
  entry_cents: number;
  payout_cents: number;
  outcome: string;
  matches: AdminTournamentLogMatch[];
}

export interface AdminTournamentLog {
  tournament_id: string;
  tournament_outcome: string | null;
  recorded_at: string | null;
  entrants: AdminTournamentLogEntrant[];
}

export function useTournamentLog(tournamentId: string | null) {
  return useQuery({
    queryKey: ['admin', 'tournament-log', tournamentId],
    enabled: !!tournamentId,
    queryFn: async (): Promise<AdminTournamentLog> => {
      const { data, error } = await api.GET(
        '/api/v1/admin/tournaments/{tournament_id}/log',
        { params: { path: { tournament_id: tournamentId! } } },
      );
      if (error) throw new Error('Failed to load the tournament log');
      return data as AdminTournamentLog;
    },
  });
}
