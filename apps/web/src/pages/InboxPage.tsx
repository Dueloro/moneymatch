import { EmptyState } from '../components/ui/EmptyState';

export function InboxPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Inbox</h1>
      <EmptyState title="No notifications" subline="You're all caught up." />
    </div>
  );
}
