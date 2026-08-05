import type { ReactNode } from 'react';

import type { Conversation } from '../../hooks/useChat';
import { formatRelativeTime } from '../../lib/format';
import { Badge } from '../ui/Badge';
import { Avatar } from './Avatar';
import { BellIcon } from '../ui/icons';
import { LifebuoyIcon, PlusIcon } from './icons';

/** What the right pane is showing. `notifications` is the pinned feed. */
export type Selection =
  { type: 'notifications' } | { type: 'conversation'; id: string };

function Row({
  active,
  avatar,
  title,
  subline,
  meta,
  unread,
  onClick,
}: {
  active: boolean;
  avatar: ReactNode;
  title: string;
  subline: string;
  meta?: string;
  unread: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active}
      className={[
        'flex w-full items-center gap-3.5 rounded-inset border-l-2 px-3.5 py-3 text-left transition',
        active
          ? 'border-l-line-strong bg-panel-raised'
          : 'border-l-transparent hover:bg-panel-raised/50',
      ].join(' ')}
    >
      {avatar}
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline gap-2">
          <span className="truncate text-sm font-semibold text-text">{title}</span>
          {meta && (
            <span className="ml-auto shrink-0 text-micro text-text-tertiary">
              {meta}
            </span>
          )}
        </span>
        <span
          className={[
            'mt-1 block truncate text-xs leading-snug',
            unread > 0 ? 'font-medium text-text' : 'text-text-secondary',
          ].join(' ')}
        >
          {subline}
        </span>
      </span>
      <Badge count={unread} />
    </button>
  );
}

/**
 * The left rail: the pinned Notifications feed and Support thread, then every
 * direct message. Notifications keep their home here — the Inbox now holds both
 * the feed and the conversations.
 */
export function ConversationList({
  conversations,
  selection,
  onSelect,
  notificationsUnread,
  notificationsPreview,
  onOpenSupport,
  supportPending,
  onNewMessage,
  error,
}: {
  conversations: Conversation[];
  selection: Selection;
  onSelect: (selection: Selection) => void;
  notificationsUnread: number;
  notificationsPreview: string;
  onOpenSupport: () => void;
  supportPending: boolean;
  onNewMessage: () => void;
  /** Why a thread wouldn't open (a stale deep link, a closed friendship). */
  error?: string | null;
}) {
  const support = conversations.find((c) => c.kind === 'support');
  const dms = conversations.filter((c) => c.kind === 'dm');

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-hairline px-4 pb-3.5 pt-4">
        <h2 className="label-money !text-xs">Inbox</h2>
        <button
          type="button"
          onClick={onNewMessage}
          className="flex items-center gap-1.5 rounded-pill border border-hairline px-3 py-1.5 text-xs font-semibold text-text-secondary transition hover:border-line-strong hover:text-text"
        >
          <PlusIcon className="h-3.5 w-3.5" />
          New message
        </button>
      </div>

      {error && (
        <p
          role="alert"
          className="border-b border-hairline px-4 py-2.5 text-xs text-red"
        >
          {error}
        </p>
      )}

      <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto px-2 py-2">
        <Row
          active={selection.type === 'notifications'}
          avatar={
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-hairline bg-panel-raised text-text-secondary ">
              <BellIcon className="h-5 w-5" />
            </span>
          }
          title="Notifications"
          subline={notificationsPreview}
          unread={notificationsUnread}
          onClick={() => onSelect({ type: 'notifications' })}
        />

        <Row
          active={
            selection.type === 'conversation' &&
            !!support &&
            selection.id === support.id
          }
          avatar={
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-hairline bg-panel-raised text-text-secondary">
              <LifebuoyIcon className="h-5 w-5" />
            </span>
          }
          title="MoneyMatch Support"
          subline={
            support?.last_message_preview ??
            (supportPending ? 'Opening…' : 'Questions about a contest or payout')
          }
          meta={
            support?.last_message_at
              ? formatRelativeTime(support.last_message_at)
              : undefined
          }
          unread={support?.unread ?? 0}
          onClick={() =>
            support
              ? onSelect({ type: 'conversation', id: support.id })
              : onOpenSupport()
          }
        />

        <p className="label-money px-4 pb-1.5 pt-5">Direct messages</p>
        {dms.length === 0 ? (
          <p className="px-4 py-2 text-xs text-text-secondary">
            No conversations yet. Start one with a friend.
          </p>
        ) : (
          dms.map((c) => (
            <Row
              key={c.id}
              active={selection.type === 'conversation' && selection.id === c.id}
              avatar={<Avatar name={c.title} online={c.online} showPresence />}
              title={c.title}
              subline={c.last_message_preview ?? 'Say hi'}
              meta={
                c.last_message_at ? formatRelativeTime(c.last_message_at) : undefined
              }
              unread={c.unread}
              onClick={() => onSelect({ type: 'conversation', id: c.id })}
            />
          ))
        )}
      </div>
    </div>
  );
}
