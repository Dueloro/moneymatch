import type { components } from '@moneymatch/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../lib/api';
import { messageOf } from '../lib/apiError';
import { track } from '../lib/telemetry';

export type ChallengeView = components['schemas']['ChallengeView'];

export type ChallengeCreated = components['schemas']['ChallengeCreatedResponse'];

export type ChallengePreview = components['schemas']['ChallengePreviewResponse'];

export type CreateChallengeVars = components['schemas']['CreateChallengeRequest'];

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ['notifications'] });
    qc.invalidateQueries({ queryKey: ['activity'] });
    qc.invalidateQueries({ queryKey: ['me'] });
  };
}

export function useCreateChallenge() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (vars: CreateChallengeVars): Promise<ChallengeCreated> => {
      const { data, error } = await api.POST('/api/v1/challenges', { body: vars });
      if (error) throw new Error(messageOf(error, 'Could not create the challenge.'));
      return data;
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

export function useInvitePreview(token: string | undefined) {
  return useQuery({
    queryKey: ['invite', token],
    enabled: !!token,
    queryFn: async (): Promise<ChallengePreview> => {
      const { data, error } = await api.GET('/api/v1/challenges/token/{token}', {
        params: { path: { token: token! } },
      });
      if (error) throw new Error('This invite link is invalid or expired.');
      return data;
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
