import { useEffect, useRef, useState } from 'react';

import {
  useMarkConversationRead,
  useThread,
  type ChatMessage,
} from '../../hooks/useChat';
import { ChallengeDialog } from '../ChallengeDialog';
import { Skeleton } from '../ui/Skeleton';
import { Avatar } from './Avatar';
import { Composer, type InviteChoice } from './Composer';
import { InviteSheet } from './InviteSheet';
import { MessageBubble } from './MessageBubble';
import { BackIcon, ChatIcon } from './icons';

function dayLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(date, today)) return 'Today';
  if (same(date, yesterday)) return 'Yesterday';
  return date.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

/** True when this message starts a new visual run (new sender, or 5+ min gap). */
function startsRun(message: ChatMessage, previous: ChatMessage | undefined): boolean {
  if (!previous || previous.sender_id !== message.sender_id) return true;
  const gap =
    new Date(message.created_at).getTime() - new Date(previous.created_at).getTime();
  return gap > 5 * 60 * 1000;
}

/** The open conversation: header, scrolling transcript, and the typing bar. */
export function MessageThread({
  conversationId,
  onBack,
}: {
  conversationId: string;
  /** Mobile: return to the conversation list. */
  onBack: () => void;
}) {
  const { data, isLoading } = useThread(conversationId);
  const markRead = useMarkConversationRead();
  const [invite, setInvite] = useState<InviteChoice | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const conversation = data?.conversation;
  const messages = data?.messages ?? [];
  const peerName = conversation?.title ?? 'Conversation';
  const unread = conversation?.unread ?? 0;

  // Opening a thread (or receiving into an open one) clears its badge.
  useEffect(() => {
    if (unread > 0) markRead.mutate(conversationId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, unread]);

  // Pin to the newest message as the transcript grows. (jsdom has no
  // scrollIntoView, hence the guard — tests render the same component.)
  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: 'end' });
  }, [messages.length, conversationId]);

  return (
    <section
      className="flex h-full min-h-0 flex-col"
      aria-label={`Chat with ${peerName}`}
    >
      <header className="flex items-center gap-3.5 border-b border-hairline bg-panel px-5 py-4">
        <button
          type="button"
          onClick={onBack}
          aria-label="Back to conversations"
          className="grid h-9 w-9 place-items-center rounded-full text-text-secondary transition hover:bg-panel-raised hover:text-text md:hidden"
        >
          <BackIcon className="h-5 w-5" />
        </button>
        <Avatar
          name={peerName}
          online={conversation?.online ?? false}
          showPresence
          brand={conversation?.kind === 'support'}
        />
        <div className="min-w-0">
          <p className="truncate text-base font-bold text-text">{peerName}</p>
          <p className="flex items-center gap-1.5 text-xs text-text-secondary">
            {conversation?.kind !== 'support' && (
              <span
                aria-hidden
                className={[
                  'h-1.5 w-1.5 rounded-full',
                  conversation?.online ? 'bg-live' : 'bg-text-tertiary',
                ].join(' ')}
              />
            )}
            {conversation?.kind === 'support'
              ? 'Usually replies within a few hours'
              : conversation?.online
                ? 'Active now'
                : 'Offline'}
          </p>
        </div>
      </header>

      <div className="no-scrollbar flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto px-5 py-5">
        {isLoading && (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-12 w-56 rounded-card" />
            <Skeleton className="h-12 w-72 self-end rounded-card" />
            <Skeleton className="h-12 w-48 rounded-card" />
          </div>
        )}

        {!isLoading && messages.length === 0 && (
          <div className="m-auto max-w-xs text-center">
            <span className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-full border border-hairline bg-panel-raised text-text-tertiary">
              <ChatIcon className="h-6 w-6" />
            </span>
            <p className="text-sm font-semibold text-text">No messages yet</p>
            <p className="mt-1 text-xs text-text-secondary">
              Say hi, or send {peerName} an invite with the + button.
            </p>
          </div>
        )}

        {messages.map((message, i) => {
          const previous = messages[i - 1];
          const newDay =
            !previous ||
            new Date(previous.created_at).toDateString() !==
              new Date(message.created_at).toDateString();
          return (
            <div key={message.id} className="flex flex-col gap-2.5">
              {newDay && (
                <div className="my-3 flex items-center gap-3">
                  <span className="h-px flex-1 bg-hairline" />
                  <span className="text-micro uppercase tracking-[0.14em] text-text-tertiary">
                    {dayLabel(message.created_at)}
                  </span>
                  <span className="h-px flex-1 bg-hairline" />
                </div>
              )}
              <MessageBubble
                message={message}
                showAvatar={startsRun(message, previous)}
                peerName={peerName}
              />
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      <Composer
        conversationId={conversationId}
        canInvite={conversation?.kind === 'dm'}
        onPickInvite={setInvite}
      />

      {(invite === 'pool' || invite === 'tournament') && (
        <InviteSheet
          conversationId={conversationId}
          kind={invite}
          peerName={peerName}
          onClose={() => setInvite(null)}
        />
      )}
      {invite === 'h2h' && conversation?.peer_user_id && (
        <ChallengeDialog
          friend={{
            user_id: conversation.peer_user_id,
            username: conversation.peer_username,
          }}
          onClose={() => setInvite(null)}
        />
      )}
    </section>
  );
}
