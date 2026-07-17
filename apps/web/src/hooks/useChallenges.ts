import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../lib/api';
import { track } from '../lib/telemetry';

// Mirrors schemas/social.py. Requests carry ids/presets only.

export interface ChallengeView {
  id: string;
  challenger_id: string;
  challenger_username: string | null;
  challengee_id: string | null;
  game: string;
  market: string;
  market_label: string;
  kind: string;
  speed: string | null;
  entry_cents: number;
  friendly: boolean;
  state: string;
  match_id: string | null;
  is_invite: boolean;
  expires_at: string;
}

export interface ChallengeCreated {
  challenge: ChallengeView;
  invite_token: string | null;
  invite_path: string | null;
}

export interface ChallengePreview {
  game: string;
  market: string;
  market_label: string;
  kind: string;
  speed: string | null;
  entry_cents: number;
  challenger_username: string | null;
  state: string;
  valid: boolean;
  expires_at: string;
}

export interface CreateChallengeVars {
  challengee_id?: string;
  rematch_of?: string;
  game?: string;
  market?: string;
  speed?: string;
  entry_preset_cents?: number;
}

function messageOf(error: unknown, fallback: string): string {
  const msg = (error as { message?: string } | undefined)?.message;
  return typeof msg === 'string' && msg ? msg : fallback;
}

function useInvalidate() {
  const qc = useQueryClient();
  // Key by prefix so these work without the auth context (and match any user id).
  return () => {
    qc.invalidateQueries({ queryKey: ['notifications'] });
    qc.invalidateQueries({ queryKey: ['activity'] });
    qc.invalidateQueries({ queryKey: ['me'] });
  };
}

/** Create a challenge: direct (challengee_id), rematch (rematch_of), or invite. */
export function useCreateChallenge() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (vars: CreateChallengeVars): Promise<ChallengeCreated> => {
      const { data, error } = await api.POST('/api/v1/challenges', { body: vars });
      if (error) throw new Error(messageOf(error, 'Could not create the challenge.'));
      return data as ChallengeCreated;
    },
    onSuccess: (_data, vars) => {
      if (vars.rematch_of) track('rematch_sent');
      else if (vars.challengee_id) track('challenge_sent');
      else track('invite_created');
      invalidate();
    },
  });
}

export function useAcceptChallenge() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (challengeId: string): Promise<{ match_id: string }> => {
      const { data, error } = await api.POST(
        '/api/v1/challenges/{challenge_id}/accept',
        {
          params: { path: { challenge_id: challengeId } },
        },
      );
      if (error) throw new Error(messageOf(error, 'Could not accept.'));
      return data as { match_id: string };
    },
    onSuccess: () => {
      track('challenge_accepted');
      invalidate();
    },
  });
}

export function useDeclineChallenge() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (challengeId: string): Promise<void> => {
      const { error } = await api.POST('/api/v1/challenges/{challenge_id}/decline', {
        params: { path: { challenge_id: challengeId } },
      });
      if (error) throw new Error(messageOf(error, 'Could not decline.'));
    },
    onSuccess: invalidate,
  });
}

/** Public invite preview (no auth) — funnel step 1. */
export function useInvitePreview(token: string | undefined) {
  return useQuery({
    queryKey: ['invite', token],
    enabled: !!token,
    queryFn: async (): Promise<ChallengePreview> => {
      const { data, error } = await api.GET('/api/v1/challenges/token/{token}', {
        params: { path: { token: token! } },
      });
      if (error) throw new Error('This invite link is invalid or expired.');
      return data as ChallengePreview;
    },
  });
}

export function useAcceptInvite() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (token: string): Promise<{ match_id: string }> => {
      const { data, error } = await api.POST(
        '/api/v1/challenges/token/{token}/accept',
        {
          params: { path: { token } },
        },
      );
      if (error) throw new Error(messageOf(error, 'Could not accept the invite.'));
      return data as { match_id: string };
    },
    onSuccess: () => {
      track('invite_accepted');
      invalidate();
    },
  });
}
