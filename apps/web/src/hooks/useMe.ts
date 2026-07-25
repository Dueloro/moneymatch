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
  /** Self-imposed cool-off end (ISO); staking is refused until it passes. */
  timeout_until: string | null;
}

/** First-match funnel progress — drives the getting-started checklist. */
export interface GettingStarted {
  picked_games: boolean;
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
    /** Catalog game ids the player has chosen to play (their "play set"). */
    active_games: string[];
  };
  needs_onboarding: boolean;
  limits: Limits | null;
  unread_notifications: number;
  getting_started: GettingStarted | null;
}

/** Fetches `/me` once the user is authenticated. Provisions the row server-side. */
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

/** Irreversibly self-exclude (freeze staking). Refreshes `/me` on success. */
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
 * Set the player's play set (the games shown in the switcher). Sends the full
 * list — the server dedupes and validates each id against the catalog. Refreshes
 * `/me` so the switcher and Profile update immediately.
 */
export function useSetActiveGames() {
  const qc = useQueryClient();
  const { session } = useAuth();
  return useMutation({
    mutationFn: async (games: string[]): Promise<void> => {
      const { error } = await api.PATCH('/api/v1/me', {
        body: { active_games: games },
      });
      if (error) throw new Error('Could not save your games');
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['me', session?.user.id] }),
  });
}

/**
 * Update the player's protective staking caps (daily loss / entry, in cents).
 * The server applies a lowering instantly and defers a raise 24 h, so the fresh
 * `/me` reflects either the new cap or a `pending_limits` entry.
 */
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
