import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { useConversations, useOpenConversation } from '../../hooks/useChat';
import { useNotifications } from '../../hooks/useNotifications';
import { NotificationsFeed } from '../NotificationsFeed';
import { BellIcon } from '../ui/icons';
import { ConversationList, type Selection } from './ConversationList';
import { MessageThread } from './MessageThread';
import { NewMessageSheet } from './NewMessageSheet';

export function ChatPanel() {
  const [params, setParams] = useSearchParams();
  const { data, isLoading } = useConversations();
  const notifications = useNotifications();
  const open = useOpenConversation();

  const [selection, setSelection] = useState<Selection>({ type: 'notifications' });
  const [showPicker, setShowPicker] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);
  const [mobilePane, setMobilePane] = useState<'list' | 'detail'>('list');

  const conversations = data?.conversations ?? [];
  const deepLinkUser = params.get('dm');

  useEffect(() => {
    if (!deepLinkUser || open.isPending) return;
    void open.mutateAsync({ userId: deepLinkUser }).then(
      (conversation) => {
        setOpenError(null);
        setSelection({ type: 'conversation', id: conversation.id });
        setMobilePane('detail');
      },
      (err: Error) => {
        setOpenError(err.message);
      },
    );
    params.delete('dm');
    setParams(params, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLinkUser]);

  function select(next: Selection) {
    setSelection(next);
    setMobilePane('detail');
  }

  async function openSupport() {
    try {
      const conversation = await open.mutateAsync({ support: true });
      setOpenError(null);
      select({ type: 'conversation', id: conversation.id });
    } catch (err) {
      setOpenError((err as Error).message);
    }
  }

  async function pickFriend(userId: string) {
    try {
      const conversation = await open.mutateAsync({ userId });
      setOpenError(null);
      select({ type: 'conversation', id: conversation.id });
      setShowPicker(false);
    } catch (err) {
      setOpenError((err as Error).message);
    }
  }

  const unreadNotifications = notifications.data?.unread ?? 0;
  const notificationsPreview = isLoading
    ? 'Loading…'
    : unreadNotifications > 0
      ? `${unreadNotifications} new`
      : 'Match, challenge, and payout updates';

  return (
    <div
      data-testid="chat-panel"
      className="h-[calc(100dvh-13rem)] min-h-[28rem] overflow-hidden rounded-card border border-hairline bg-panel shadow-overlay md:grid md:h-[calc(100vh-11rem)] md:min-h-[36rem] md:grid-cols-[20rem_minmax(0,1fr)]"
    >
      <div
        className={[
          'h-full min-h-0 border-hairline bg-bg md:block md:border-r',
          mobilePane === 'list' ? 'block' : 'hidden',
        ].join(' ')}
      >
        <ConversationList
          error={showPicker ? null : openError}
          conversations={conversations}
          selection={selection}
          onSelect={select}
          notificationsUnread={unreadNotifications}
          notificationsPreview={notificationsPreview}
          onOpenSupport={() => void openSupport()}
          supportPending={open.isPending}
          onNewMessage={() => setShowPicker(true)}
        />
      </div>

      <div
        className={[
          'h-full min-h-0 min-w-0 md:block',
          mobilePane === 'detail' ? 'block' : 'hidden',
        ].join(' ')}
      >
        {selection.type === 'notifications' ? (
          <div className="flex h-full min-h-0 flex-col">
            <header className="flex items-center gap-3.5 border-b border-hairline bg-panel px-5 py-4">
              <button
                type="button"
                onClick={() => setMobilePane('list')}
                className="text-sm font-semibold text-text-secondary md:hidden"
              >
                ← Inbox
              </button>
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-hairline bg-panel-raised text-text-secondary">
                <BellIcon className="h-5 w-5" />
              </span>
              <div>
                <p className="text-base font-bold text-text">Notifications</p>
                <p className="text-xs text-text-secondary">
                  Everything the platform sent you
                </p>
              </div>
            </header>
            <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto px-5 py-5">
              <NotificationsFeed />
            </div>
          </div>
        ) : (
          <MessageThread
            key={selection.id}
            conversationId={selection.id}
            onBack={() => setMobilePane('list')}
          />
        )}
      </div>

      {showPicker && (
        <NewMessageSheet
          pending={open.isPending}
          error={openError}
          onPick={(userId) => void pickFriend(userId)}
          onClose={() => {
            setOpenError(null);
            setShowPicker(false);
          }}
        />
      )}
    </div>
  );
}
