import type { components } from '@moneymatch/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';
import { messageOf } from '../lib/apiError';
import { setLinkReturnTo } from '../lib/linkReturnTo';

export type FormatStat = components['schemas']['FormatStat'];

export type ProfileSnapshot = components['schemas']['ProfileSnapshot'];

export type LinkStatus = 'LINKED' | 'BLOCKED' | 'UNLINKED';

export type GameLink = components['schemas']['GameLink'];

export type LinksResponse = components['schemas']['LinksResponse'];

const linksKey = (userId?: string) => ['links', userId];

export function useLinks() {
  const { session } = useAuth();
  return useQuery({
    queryKey: linksKey(session?.user.id),
    enabled: !!session,
    queryFn: async (): Promise<LinksResponse> => {
      const { data, error } = await api.GET('/api/v1/links');
      if (error) throw new Error('Failed to load linked games');
      return data;
    },
  });
}

function useLinksInvalidation() {
  const qc = useQueryClient();
  const { session } = useAuth();
  return () => {
    qc.invalidateQueries({ queryKey: linksKey(session?.user.id) });
  };
}

export function useConnectLichess() {
  return useMutation({
    mutationFn: async (returnTo: string | null): Promise<void> => {
      const { data, error } = await api.POST('/api/v1/links/lichess/oauth/start');
      if (error || !data) throw new Error(messageOf(error, 'Could not reach Lichess.'));
      if (returnTo) setLinkReturnTo(returnTo);
      window.location.assign(data.authorize_url);
    },
  });
}

export function useCompleteLichessLink() {
  const invalidate = useLinksInvalidation();
  return useMutation({
    mutationFn: async (vars: {
      code: string;
      state: string;
    }): Promise<LinksResponse> => {
      const { data, error } = await api.POST('/api/v1/links/lichess/oauth/callback', {
        body: vars,
      });
      if (error) throw new Error(messageOf(error, 'Could not connect Lichess.'));
      return data;
    },
    onSuccess: invalidate,
  });
}

export function useRefreshLink() {
  const invalidate = useLinksInvalidation();
  return useMutation({
    mutationFn: async (game: string): Promise<LinksResponse> => {
      const { data, error } = await api.GET('/api/v1/links/{game}/profile', {
        params: { path: { game } },
      });
      if (error) throw new Error(messageOf(error, 'Could not refresh.'));
      return data;
    },
    onSuccess: invalidate,
  });
}
