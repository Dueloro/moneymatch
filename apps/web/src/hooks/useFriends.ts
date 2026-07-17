import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';
import { track } from '../lib/telemetry';

// Mirrors schemas/social.py. The server owns entry cents, expiry, and matching;
// the client sends only a username/code or ids.

export interface FriendItem {
  friendship_id: string;
  user_id: string;
  username: string | null;
  online: boolean;
}

export interface FriendsResponse {
  your_friend_code: string;
  friends: FriendItem[];
  incoming: FriendItem[];
  outgoing: FriendItem[];
}

function messageOf(error: unknown, fallback: string): string {
  const msg = (error as { message?: string } | undefined)?.message;
  return typeof msg === 'string' && msg ? msg : fallback;
}

/** Friends list + pending requests. Polls slowly for presence (green dot). */
export function useFriends() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['friends', session?.user.id],
    enabled: !!session,
    refetchInterval: 30000,
    queryFn: async (): Promise<FriendsResponse> => {
      const { data, error } = await api.GET('/api/v1/friends');
      if (error) throw new Error('Failed to load friends');
      return data as FriendsResponse;
    },
  });
}

function useFriendsInvalidation() {
  const qc = useQueryClient();
  const { session } = useAuth();
  return () => qc.invalidateQueries({ queryKey: ['friends', session?.user.id] });
}

export function useAddFriend() {
  const invalidate = useFriendsInvalidation();
  return useMutation({
    mutationFn: async (usernameOrCode: string): Promise<void> => {
      const { error } = await api.POST('/api/v1/friends', {
        body: { username_or_code: usernameOrCode },
      });
      if (error) throw new Error(messageOf(error, 'Could not add that player.'));
    },
    onSuccess: () => {
      track('friend_added');
      invalidate();
    },
  });
}

export function useRespondFriend() {
  const invalidate = useFriendsInvalidation();
  return useMutation({
    mutationFn: async (vars: {
      friendshipId: string;
      action: 'accept' | 'decline' | 'block';
    }): Promise<void> => {
      const { error } = await api.POST(
        `/api/v1/friends/{friendship_id}/${vars.action}` as '/api/v1/friends/{friendship_id}/accept',
        { params: { path: { friendship_id: vars.friendshipId } } },
      );
      if (error) throw new Error(messageOf(error, 'Could not update the request.'));
    },
    onSuccess: invalidate,
  });
}

export function useRemoveFriend() {
  const invalidate = useFriendsInvalidation();
  return useMutation({
    mutationFn: async (friendshipId: string): Promise<void> => {
      const { error } = await api.DELETE('/api/v1/friends/{friendship_id}', {
        params: { path: { friendship_id: friendshipId } },
      });
      if (error) throw new Error(messageOf(error, 'Could not remove.'));
    },
    onSuccess: invalidate,
  });
}
