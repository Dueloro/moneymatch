import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

export interface Limits {
  daily_loss_cap_cents: number;
  daily_entry_cap_cents: number;
  max_concurrent_contests: number;
  pending_limits: Record<string, number> | null;
  pending_effective_at: string | null;
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
  };
  needs_onboarding: boolean;
  limits: Limits | null;
  unread_notifications: number;
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
