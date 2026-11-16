import type { components } from '@moneymatch/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../lib/api';
import { messageOf } from '../lib/apiError';

export type FlagItem = components['schemas']['FlagItem'];

export type AdminUserSummary = components['schemas']['AdminUserSummary'];

export type AdminContestListItem = components['schemas']['AdminContestListItem'];

export type AdminSupportThread = components['schemas']['SupportThreadItem'];

export type AdminSupportMessage = components['schemas']['SupportMessageItem'];

export type AdminSupportDetail = components['schemas']['SupportThreadDetail'];

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

export function useAdminSupportThreads() {
  return useQuery({
    queryKey: ['admin', 'support'],
    refetchInterval: 10000,
    queryFn: async (): Promise<AdminSupportThread[]> => {
      const { data, error } = await api.GET('/api/v1/admin/support');
      if (error) throw new Error('Failed to load support threads');
      return data;
    },
  });
}

export function useAdminSupportThread(conversationId: string | null) {
  return useQuery({
    queryKey: ['admin', 'support', conversationId],
    enabled: !!conversationId,
    refetchInterval: 6000,
    queryFn: async (): Promise<AdminSupportDetail> => {
      const { data, error } = await api.GET('/api/v1/admin/support/{conversation_id}', {
        params: { path: { conversation_id: conversationId! } },
      });
      if (error) throw new Error('Failed to load support thread');
      return data;
    },
  });
}

export function useReplyToSupport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      conversationId: string;
      body: string;
    }): Promise<AdminSupportDetail> => {
      const { data, error } = await api.POST(
        '/api/v1/admin/support/{conversation_id}/reply',
        {
          params: { path: { conversation_id: input.conversationId } },
          body: { body: input.body },
        },
      );
      if (error) throw new Error(messageOf(error, 'Reply failed'));
      return data;
    },
    onSuccess: (data) => {
      qc.setQueryData(['admin', 'support', data.conversation_id], data);
      qc.invalidateQueries({ queryKey: ['admin', 'support'] });
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
      if (error) throw new Error(messageOf(error, 'Failed to update flag'));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'flags'] }),
  });
}

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
      if (error) throw new Error(messageOf(error, 'Action failed'));
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
      if (error) throw new Error(messageOf(error, 'Adjustment failed'));
    },
    onSuccess: refresh,
  });
}

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
      if (error) throw new Error(messageOf(error, 'Resettle failed'));
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
      if (error) throw new Error(messageOf(error, 'Void failed'));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin'] }),
  });
}

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
      if (error) throw new Error(messageOf(error, 'Clear failed'));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'risk'] }),
  });
}

export type AdminDispute = components['schemas']['AdminDisputeItem'];

export function useAdminDisputes() {
  return useQuery({
    queryKey: ['admin', 'disputes'],
    refetchInterval: 10000,
    queryFn: async (): Promise<AdminDispute[]> => {
      const { data, error } = await api.GET('/api/v1/admin/disputes');
      if (error) throw new Error('Failed to load disputes');
      return data;
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
      if (error) throw new Error(messageOf(error, 'Resolve failed'));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'disputes'] }),
  });
}
