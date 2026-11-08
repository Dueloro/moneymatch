import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

interface InboxBadge {
  badge: number;
}

function useBadgeKey() {
  const { session } = useAuth();
  return ['inbox-badge', session?.user.id] as const;
}

/** Unread DMs + notifications that arrived since Social was last opened. */
export function useInboxBadge(): number {
  const { session } = useAuth();
  const key = useBadgeKey();
  const query = useQuery({
    queryKey: key,
    enabled: !!session,
    refetchInterval: 15000,
    queryFn: async (): Promise<InboxBadge> => {
      const { data, error } = await api.GET('/api/v1/inbox/badge');
      if (error) throw new Error('Failed to load inbox badge');
      return data as InboxBadge;
    },
  });
  return query.data?.badge ?? 0;
}

export function useMarkInboxSeen() {
  const qc = useQueryClient();
  const key = useBadgeKey();
  return useMutation({
    mutationFn: async (): Promise<InboxBadge> => {
      const { data, error } = await api.POST('/api/v1/inbox/seen');
      if (error) throw new Error('Could not update inbox');
      return data as InboxBadge;
    },
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: key });
      qc.setQueryData<InboxBadge>(key, { badge: 0 });
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}
