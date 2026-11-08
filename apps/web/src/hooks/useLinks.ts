import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';
import { setLinkReturnTo } from '../lib/linkReturnTo';

export interface FormatStat {
  speed: string;
  rating: number;
  games: number;
  provisional: boolean;
}

export interface ProfileSnapshot {
  username: string;
  display_name: string;
  url: string;
  link_method: string;
  game: string;
  account_age_days: number | null;
  win_rate: number;
  draw_rate: number;
  total_games: number;
  formats: FormatStat[];
  primary_speed: string | null;
  rating: number | null;
  avatar_url: string | null;
}

export type LinkStatus = 'LINKED' | 'BLOCKED' | 'UNLINKED';

export interface GameLink {
  game: string;
  display_name: string;
  status: LinkStatus;
  host_username: string | null;
  linked_at: string | null;
  profile: ProfileSnapshot | null;
  win_streak: number;
}

export interface LinksResponse {
  games: GameLink[];
}

const linksKey = (userId?: string) => ['links', userId];

export function useLinks() {
  const { session } = useAuth();
  return useQuery({
    queryKey: linksKey(session?.user.id),
    enabled: !!session,
    queryFn: async (): Promise<LinksResponse> => {
      const { data, error } = await api.GET('/api/v1/links');
      if (error) throw new Error('Failed to load linked games');
      return data as LinksResponse;
    },
  });
}

function messageOf(error: unknown, fallback: string): string {
  const msg = (error as { message?: string } | undefined)?.message;
  return typeof msg === 'string' && msg ? msg : fallback;
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
      return data as LinksResponse;
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
      return data as LinksResponse;
    },
    onSuccess: invalidate,
  });
}
