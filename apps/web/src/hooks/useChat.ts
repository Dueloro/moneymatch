import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { api } from '../lib/api';
import { track } from '../lib/telemetry';
import { useNotifications } from './useNotifications';

// Mirrors schemas/chat.py. The client sends a body, a friend id, or a preset
// choice — the server owns timestamps, invite state, and match formation.

export type MessageKind = 'text' | 'invite' | 'system';
export type InviteKind = 'pool' | 'tournament' | 'h2h';
export type InviteStatus = 'pending' | 'accepted' | 'declined' | 'expired';

/** The invite card's whole contract, carried on an `invite` message. */
export interface InvitePayload {
  invite_kind?: InviteKind;
  title?: string;
  game?: string;
  metric?: string | null;
  difficulty?: string | null;
  market?: string | null;
  market_label?: string | null;
  entry_cents?: number;
  friendly?: boolean;
  status?: InviteStatus;
  challenge_id?: string;
  match_id?: string;
  redirect_path?: string;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  sender_id: string | null;
  sender_username: string | null;
  mine: boolean;
  kind: MessageKind;
  body: string | null;
  payload: InvitePayload;
  created_at: string;
}

export interface Conversation {
  id: string;
  kind: 'dm' | 'support';
  title: string;
  peer_user_id: string | null;
  peer_username: string | null;
  online: boolean;
  unread: number;
  last_message_at: string | null;
  last_message_preview: string | null;
}

export interface ConversationsResponse {
  unread_total: number;
  conversations: Conversation[];
}

export interface Thread {
  conversation: Conversation;
  messages: ChatMessage[];
}

function messageOf(error: unknown, fallback: string): string {
  const msg = (error as { message?: string } | undefined)?.message;
  return typeof msg === 'string' && msg ? msg : fallback;
}

function useChatKeys() {
  const { session } = useAuth();
  return {
    conversations: ['chat', 'conversations', session?.user.id] as const,
    thread: (id: string | null) => ['chat', 'thread', session?.user.id, id] as const,
  };
}

/** The conversation list. Polls like the other social surfaces. */
export function useConversations() {
  const { session } = useAuth();
  const keys = useChatKeys();
  return useQuery({
    queryKey: keys.conversations,
    enabled: !!session,
    refetchInterval: 15000,
    queryFn: async (): Promise<ConversationsResponse> => {
      const { data, error } = await api.GET('/api/v1/chat/conversations');
      if (error) throw new Error('Failed to load messages');
      return data as ConversationsResponse;
    },
  });
}

/**
 * Everything the Inbox would badge you for: unread notifications **and** unread
 * messages. Both queries poll on their own, so this is live wherever it's
 * mounted — the nav bell, and the Social page's Inbox tab.
 */
export function useInboxUnread(): number {
  const chat = useConversations();
  const notifications = useNotifications();
  return (chat.data?.unread_total ?? 0) + (notifications.data?.unread ?? 0);
}

/** One open thread. Polls faster — this is the surface you watch. */
export function useThread(conversationId: string | null) {
  const { session } = useAuth();
  const keys = useChatKeys();
  return useQuery({
    queryKey: keys.thread(conversationId),
    enabled: !!session && !!conversationId,
    refetchInterval: 6000,
    queryFn: async (): Promise<Thread> => {
      const { data, error } = await api.GET(
        '/api/v1/chat/conversations/{conversation_id}',
        { params: { path: { conversation_id: conversationId! } } },
      );
      if (error) throw new Error('Failed to load this conversation');
      return data as Thread;
    },
  });
}

function useChatInvalidation() {
  const qc = useQueryClient();
  const keys = useChatKeys();
  return (conversationId?: string) => {
    qc.invalidateQueries({ queryKey: keys.conversations });
    if (conversationId) {
      qc.invalidateQueries({ queryKey: keys.thread(conversationId) });
    }
  };
}

/** Get-or-create a thread: a friend DM, or the support thread. */
export function useOpenConversation() {
  const invalidate = useChatInvalidation();
  return useMutation({
    mutationFn: async (
      target: { userId: string } | { support: true },
    ): Promise<Conversation> => {
      const body =
        'support' in target
          ? { kind: 'support' as const }
          : { kind: 'dm' as const, user_id: target.userId };
      const { data, error } = await api.POST('/api/v1/chat/conversations', { body });
      if (error) throw new Error(messageOf(error, 'Could not open that conversation.'));
      return data as Conversation;
    },
    onSuccess: (conversation) => invalidate(conversation.id),
  });
}

export interface SendVars {
  conversationId: string;
  body?: string;
  invite?: {
    invite_kind: 'pool' | 'tournament';
    game: string;
    entry_preset_cents: number;
    metric?: string | null;
    difficulty?: string | null;
  };
}

/** Post a typed line or an invite card. Returns the refreshed thread. */
export function useSendMessage() {
  const qc = useQueryClient();
  const keys = useChatKeys();
  const invalidate = useChatInvalidation();
  return useMutation({
    mutationFn: async (vars: SendVars): Promise<Thread> => {
      const { data, error } = await api.POST(
        '/api/v1/chat/conversations/{conversation_id}/messages',
        {
          params: { path: { conversation_id: vars.conversationId } },
          body: vars.invite ? { invite: vars.invite } : { body: vars.body ?? '' },
        },
      );
      if (error) throw new Error(messageOf(error, 'Message not sent.'));
      return data as Thread;
    },
    onSuccess: (thread, vars) => {
      // Paint the server's thread immediately, then refresh the list ordering.
      qc.setQueryData(keys.thread(vars.conversationId), thread);
      if (vars.invite) track('chat_invite_sent', { kind: vars.invite.invite_kind });
      invalidate();
    },
  });
}

/** Accept or decline an invite card inside a thread. */
export function useRespondInvite() {
  const invalidate = useChatInvalidation();
  return useMutation({
    mutationFn: async (vars: {
      conversationId: string;
      messageId: string;
      action: 'accept' | 'decline';
    }): Promise<{ match_id: string | null; redirect_path: string | null }> => {
      const { data, error } = await api.POST(
        '/api/v1/chat/messages/{message_id}/respond',
        {
          params: { path: { message_id: vars.messageId } },
          body: { action: vars.action },
        },
      );
      if (error) throw new Error(messageOf(error, 'Could not respond to that invite.'));
      return data as { match_id: string | null; redirect_path: string | null };
    },
    onSuccess: (_data, vars) => invalidate(vars.conversationId),
  });
}

/** Clear a thread's unread badge (fired when you open it). */
export function useMarkConversationRead() {
  const invalidate = useChatInvalidation();
  return useMutation({
    mutationFn: async (conversationId: string): Promise<void> => {
      const { error } = await api.POST(
        '/api/v1/chat/conversations/{conversation_id}/read',
        { params: { path: { conversation_id: conversationId } } },
      );
      if (error) throw new Error('Could not mark read');
    },
    onSuccess: () => invalidate(),
  });
}
