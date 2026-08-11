import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { InboxPage } from './InboxPage';

vi.mock('../hooks/useChat', async () => {
  const actual =
    await vi.importActual<typeof import('../hooks/useChat')>('../hooks/useChat');
  return {
    ...actual,
    useConversations: vi.fn(),
    useThread: vi.fn(),
    useOpenConversation: vi.fn(),
    useSendMessage: vi.fn(),
    useRespondInvite: vi.fn(),
    useMarkConversationRead: vi.fn(),
  };
});
vi.mock('../hooks/useNotifications', () => ({
  useNotifications: vi.fn(),
  useMarkNotificationsRead: vi.fn(),
}));
vi.mock('../hooks/useChallenges', () => ({
  useAcceptChallenge: vi.fn(),
  useDeclineChallenge: vi.fn(),
}));
vi.mock('../hooks/useFriends', () => ({ useFriends: vi.fn() }));

import {
  useConversations,
  useMarkConversationRead,
  useOpenConversation,
  useRespondInvite,
  useSendMessage,
  useThread,
} from '../hooks/useChat';
import { useAcceptChallenge, useDeclineChallenge } from '../hooks/useChallenges';
import { useFriends } from '../hooks/useFriends';
import { useMarkNotificationsRead, useNotifications } from '../hooks/useNotifications';

const respondAsync = vi.fn().mockResolvedValue({ match_id: null, redirect_path: null });
const markReadMutate = vi.fn();

const CONVERSATIONS = {
  unread_total: 2,
  conversations: [
    {
      id: 'c-support',
      kind: 'support' as const,
      title: 'Dueloro Support',
      peer_user_id: null,
      peer_username: null,
      online: true,
      unread: 0,
      last_message_at: new Date().toISOString(),
      last_message_preview: 'How can we help?',
    },
    {
      id: 'c-1',
      kind: 'dm' as const,
      title: 'jordn_cs',
      peer_user_id: 'u-2',
      peer_username: 'jordn_cs',
      online: true,
      unread: 2,
      last_message_at: new Date().toISOString(),
      last_message_preview: 'run it back?',
    },
  ],
};

const THREAD = {
  conversation: CONVERSATIONS.conversations[1],
  messages: [
    {
      id: 'm-1',
      conversation_id: 'c-1',
      sender_id: 'u-2',
      sender_username: 'jordn_cs',
      mine: false,
      kind: 'text' as const,
      body: 'run it back?',
      payload: {},
      created_at: new Date().toISOString(),
    },
    {
      id: 'm-2',
      conversation_id: 'c-1',
      sender_id: 'u-2',
      sender_username: 'jordn_cs',
      mine: false,
      kind: 'invite' as const,
      body: null,
      payload: {
        invite_kind: 'pool' as const,
        title: 'Solo pool · medium',
        game: 'cs2.faceit',
        entry_cents: 1000,
        status: 'pending' as const,
        redirect_path: '/pools',
      },
      created_at: new Date().toISOString(),
    },
  ],
};

describe('InboxPage (chat)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useConversations).mockReturnValue({
      data: CONVERSATIONS,
      isLoading: false,
    } as unknown as ReturnType<typeof useConversations>);
    vi.mocked(useThread).mockReturnValue({
      data: THREAD,
      isLoading: false,
    } as unknown as ReturnType<typeof useThread>);
    vi.mocked(useOpenConversation).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useOpenConversation>);
    vi.mocked(useSendMessage).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useSendMessage>);
    vi.mocked(useRespondInvite).mockReturnValue({
      mutateAsync: respondAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useRespondInvite>);
    vi.mocked(useMarkConversationRead).mockReturnValue({
      mutate: markReadMutate,
    } as unknown as ReturnType<typeof useMarkConversationRead>);
    vi.mocked(useNotifications).mockReturnValue({
      data: { unread: 1, items: [] },
    } as unknown as ReturnType<typeof useNotifications>);
    vi.mocked(useMarkNotificationsRead).mockReturnValue({
      mutate: vi.fn(),
    } as unknown as ReturnType<typeof useMarkNotificationsRead>);
    vi.mocked(useAcceptChallenge).mockReturnValue({
      mutateAsync: vi.fn(),
    } as unknown as ReturnType<typeof useAcceptChallenge>);
    vi.mocked(useDeclineChallenge).mockReturnValue({
      mutate: vi.fn(),
    } as unknown as ReturnType<typeof useDeclineChallenge>);
    vi.mocked(useFriends).mockReturnValue({
      data: { your_friend_code: 'MM-1', friends: [], incoming: [], outgoing: [] },
    } as unknown as ReturnType<typeof useFriends>);
  });

  it('opens on the notification feed, with conversations listed alongside', () => {
    renderWithProviders(<InboxPage />);
    // Notifications keep their home in the Inbox — pinned, and selected first.
    expect(screen.getByText('Everything the platform sent you')).toBeInTheDocument();
    expect(screen.getByText('jordn_cs')).toBeInTheDocument();
    expect(screen.getByText('Dueloro Support')).toBeInTheDocument();
  });

  it('opens a friend thread and renders its messages, invite card, and composer', () => {
    renderWithProviders(<InboxPage />);
    fireEvent.click(screen.getByText('jordn_cs'));

    // Scope to the thread — the list preview shows the same latest line.
    const thread = within(screen.getByLabelText('Chat with jordn_cs'));
    expect(thread.getByText('run it back?')).toBeInTheDocument();
    expect(thread.getByTestId('invite-card')).toBeInTheDocument();
    expect(thread.getByText('Solo pool · medium')).toBeInTheDocument();
    expect(thread.getByLabelText('Message')).toBeInTheDocument();
    // Opening a thread with unread messages clears its badge.
    expect(markReadMutate).toHaveBeenCalledWith('c-1');
  });

  it('joins a pool invite from inside the chat', async () => {
    renderWithProviders(<InboxPage />);
    fireEvent.click(screen.getByText('jordn_cs'));
    fireEvent.click(screen.getByRole('button', { name: 'Join' }));

    expect(respondAsync).toHaveBeenCalledWith({
      conversationId: 'c-1',
      messageId: 'm-2',
      action: 'accept',
    });
  });

  it('offers pool, tournament, and head-to-head invites next to the typing bar', () => {
    renderWithProviders(<InboxPage />);
    fireEvent.click(screen.getByText('jordn_cs'));
    fireEvent.click(screen.getByRole('button', { name: 'Send an invite' }));

    const menu = screen.getByTestId('invite-menu');
    expect(menu).toHaveTextContent('Solo pool');
    expect(menu).toHaveTextContent('Tournament');
    expect(menu).toHaveTextContent('Head-to-head');
  });
});
