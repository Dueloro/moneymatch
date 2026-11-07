import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';

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

export function useCreateLink() {
  const invalidate = useLinksInvalidation();
  return useMutation({
    mutationFn: async (vars: {
      game: string;
      username: string;
    }): Promise<LinksResponse> => {
      const { data, error } = await api.POST('/api/v1/links', { body: vars });
      if (error) throw new Error(messageOf(error, 'Could not link that account.'));
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
