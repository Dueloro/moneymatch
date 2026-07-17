import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

export interface NotificationItem {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  read: boolean;
  created_at: string;
}

export interface NotificationsResponse {
  unread: number;
  items: NotificationItem[];
}

/** The Inbox feed. Polls every 15 s (bell dot also comes from /me). */
export function useNotifications() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['notifications', session?.user.id],
    enabled: !!session,
    refetchInterval: 15000,
    queryFn: async (): Promise<NotificationsResponse> => {
      const { data, error } = await api.GET('/api/v1/notifications');
      if (error) throw new Error('Failed to load notifications');
      return data as NotificationsResponse;
    },
  });
}

export function useMarkNotificationsRead() {
  const qc = useQueryClient();
  const { session } = useAuth();
  return useMutation({
    mutationFn: async (ids?: string[]): Promise<{ unread: number }> => {
      const { data, error } = await api.POST('/api/v1/notifications/read', {
        body: ids ? { ids } : {},
      });
      if (error) throw new Error('Could not mark read');
      return data as { unread: number };
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications', session?.user.id] });
      qc.invalidateQueries({ queryKey: ['me', session?.user.id] });
    },
  });
}
