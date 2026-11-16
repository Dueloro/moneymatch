import type { components } from '@moneymatch/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

export type NotificationItem = components['schemas']['NotificationItem'];

export type NotificationsResponse = components['schemas']['NotificationsResponse'];

export function useNotifications() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['notifications', session?.user.id],
    enabled: !!session,
    refetchInterval: 15000,
    queryFn: async (): Promise<NotificationsResponse> => {
      const { data, error } = await api.GET('/api/v1/notifications');
      if (error) throw new Error('Failed to load notifications');
      return data;
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
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications', session?.user.id] });
      qc.invalidateQueries({ queryKey: ['me', session?.user.id] });
      qc.invalidateQueries({ queryKey: ['inbox-badge'] });
    },
  });
}
