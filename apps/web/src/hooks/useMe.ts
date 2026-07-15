import { useQuery } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

export interface Me {
  user: {
    id: string;
    username: string | null;
    email: string | null;
    residence_state: string | null;
    dob_attested_18plus: boolean;
    role: string;
    status: string;
    member_since: string;
  };
  needs_onboarding: boolean;
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
