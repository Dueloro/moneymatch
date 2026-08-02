import { useState } from 'react';

import { useFriends } from '../../hooks/useFriends';
import { PillButton } from '../ui/PillButton';
import { Avatar } from './Avatar';

/** Pick a friend to start (or reopen) a conversation with. Messaging follows
 * friendship, so this list is the whole address book. */
export function NewMessageSheet({
  onPick,
  onClose,
  pending,
  error,
}: {
  onPick: (userId: string) => void;
  onClose: () => void;
  pending: boolean;
  /** Why the thread couldn't be opened (e.g. the friendship just ended). */
  error?: string | null;
}) {
  const { data } = useFriends();
  const [query, setQuery] = useState('');

  const friends = (data?.friends ?? []).filter((f) =>
    (f.username ?? '').toLowerCase().includes(query.trim().toLowerCase()),
  );

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="New message"
    >
      <div
        className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-2xl border border-hairline bg-panel p-7 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.95)]"
        data-testid="new-message-sheet"
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-xl font-bold text-text">New message</h3>
          <PillButton variant="text" className="!px-2" onClick={onClose}>
            Close
          </PillButton>
        </div>

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search friends"
          aria-label="Search friends"
          className="mb-4 rounded-pill border border-hairline bg-bg px-4 py-2.5 text-[15px] text-text transition placeholder:text-text-tertiary focus:border-green/60 focus:outline-none"
        />

        {error && <p className="mb-3 text-[13px] text-red">{error}</p>}

        <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto">
          {friends.length === 0 ? (
            <p className="py-6 text-center text-sm text-text-secondary">
              {data && data.friends.length === 0
                ? 'Add a friend first — messaging follows friendship.'
                : 'No friend matches that search.'}
            </p>
          ) : (
            friends.map((f) => (
              <button
                key={f.friendship_id}
                type="button"
                disabled={pending}
                onClick={() => onPick(f.user_id)}
                className="flex w-full items-center gap-3.5 rounded-xl px-2.5 py-3 text-left transition hover:bg-panel-raised disabled:opacity-50"
              >
                <Avatar
                  name={f.username ?? 'Player'}
                  online={f.online}
                  showPresence
                  size="sm"
                />
                <span className="min-w-0">
                  <span className="block truncate text-[15px] font-semibold text-text">
                    {f.username ?? 'Player'}
                  </span>
                  <span className="block text-[13px] text-text-secondary">
                    {f.online ? 'Active now' : 'Offline'}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
