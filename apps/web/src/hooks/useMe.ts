import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

export interface Limits {
  daily_loss_cap_cents: number;
  daily_entry_cap_cents: number;
  daily_deposit_cap_cents: number;
  max_concurrent_contests: number;
  pending_limits: Record<string, number> | null;
  pending_effective_at: string | null;
  timeout_until: string | null;
}

export interface GettingStarted {
  linked_game: boolean;
  placed_wager: boolean;
  complete: boolean;
}

export interface Me {
  user: {
    id: string;
    username: string | null;
    email: string | null;
    friend_code: string;
    residence_state: string | null;
    dob_attested_18plus: boolean;
    role: string;
    status: string;
    member_since: string;
    dismissed_checklists: string[];
  };
  needs_onboarding: boolean;
  limits: Limits | null;
  unread_notifications: number;
  getting_started: GettingStarted | null;
  contested_games: string[];
}

export function useMe() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['me', session?.user.id],
    enabled: !!session,
    queryFn: async (): Promise<Me> => {
      const { data, error } = await api.GET('/api/v1/me');
      if (error) throw new Error('Failed to load profile');
      return data as Me;
    },
  });
}

export function useSelfExclude() {
  const qc = useQueryClient();
  const { session } = useAuth();
  return useMutation({
    mutationFn: async (): Promise<void> => {
      const { error } = await api.POST('/api/v1/me/self-exclude');
      if (error) throw new Error('Could not self-exclude');
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['me', session?.user.id] }),
  });
}

/**
 * Server-side so the dismissal survives reload and follows the player across
 * devices (never localStorage).
 */
export function useSetDismissedChecklists() {
  const qc = useQueryClient();
  const { session } = useAuth();
  const key = ['me', session?.user.id];
  const withGame = (me: Me | undefined, game: string): string[] =>
    Array.from(new Set([...(me?.user.dismissed_checklists ?? []), game]));
  return useMutation({
    mutationFn: async (game: string): Promise<void> => {
      const next = withGame(qc.getQueryData<Me>(key), game);
      const { error } = await api.PATCH('/api/v1/me', {
        body: { dismissed_checklists: next },
      });
      if (error) throw new Error('Could not dismiss the checklist');
    },
    onMutate: async (game: string) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<Me>(key);
      if (prev) {
        qc.setQueryData<Me>(key, {
          ...prev,
          user: { ...prev.user, dismissed_checklists: withGame(prev, game) },
        });
      }
      return { prev };
    },
    onError: (_err, _game, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}

export function useUpdateLimits() {
  const qc = useQueryClient();
  const { session } = useAuth();
  return useMutation({
    mutationFn: async (caps: {
      daily_loss_cap_cents?: number;
      daily_entry_cap_cents?: number;
      daily_deposit_cap_cents?: number;
      cooloff_days?: number;
    }): Promise<void> => {
      const { error } = await api.PATCH('/api/v1/me', { body: caps });
      if (error) throw new Error('Could not update your limits');
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['me', session?.user.id] }),
  });
}
