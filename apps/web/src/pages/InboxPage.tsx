import { ChatPanel } from '../components/chat/ChatPanel';

/**
 * Inbox (design p.11, extended): the messaging surface. Conversations with
 * friends and with support live here alongside the notification feed, which
 * keeps its home as the pinned first row of the list.
 */
export function InboxPage() {
  return <ChatPanel />;
}
