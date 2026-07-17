import { useState } from 'react';

import {
  useAddFriend,
  useFriends,
  useRemoveFriend,
  useRespondFriend,
  type FriendItem,
} from '../hooks/useFriends';
import { ChallengeDialog } from './ChallengeDialog';
import { EmptyState } from './ui/EmptyState';
import { ListRow } from './ui/ListRow';
import { PillButton } from './ui/PillButton';

/** Friends tab (design p.8): add by username/code, pending requests, and the
 * friend list with presence dots + a Challenge pill. */
export function FriendsPanel() {
  const { data } = useFriends();
  const add = useAddFriend();
  const [query, setQuery] = useState('');
  const [challengeFriend, setChallengeFriend] = useState<FriendItem | null>(null);

  async function submitAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    try {
      await add.mutateAsync(query.trim());
      setQuery('');
    } catch {
      /* error shown below */
    }
  }

  return (
    <div className="max-w-xl">
      <form onSubmit={submitAdd} className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Add by username or code (MM-…)"
          className="min-w-0 flex-1 rounded-pill border border-hairline bg-bg px-4 py-2 text-sm text-text placeholder:text-text-tertiary"
          aria-label="Add friend by username or code"
        />
        <PillButton type="submit" disabled={add.isPending || !query.trim()}>
          Add
        </PillButton>
      </form>
      {add.error && (
        <p className="mt-2 text-xs text-red">{(add.error as Error).message}</p>
      )}
      {data && (
        <p className="mt-2 text-xs text-text-secondary">
          Your friend code: <span className="text-text">{data.your_friend_code}</span>
        </p>
      )}

      {data && data.incoming.length > 0 && (
        <div className="mt-6">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-text-secondary">
            Requests
          </p>
          {data.incoming.map((f) => (
            <RequestRow key={f.friendship_id} friend={f} />
          ))}
        </div>
      )}

      <div className="mt-6">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-text-secondary">
          Friends
        </p>
        {data && data.friends.length === 0 ? (
          <EmptyState
            title="No friends yet"
            subline="Add someone by their username or MM- code to challenge them."
          />
        ) : (
          data?.friends.map((f) => (
            <FriendRow
              key={f.friendship_id}
              friend={f}
              onChallenge={setChallengeFriend}
            />
          ))
        )}
      </div>

      {data && data.outgoing.length > 0 && (
        <div className="mt-6">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-text-secondary">
            Sent
          </p>
          {data.outgoing.map((f) => (
            <ListRow
              key={f.friendship_id}
              title={f.username ?? 'Player'}
              subline="Pending"
            />
          ))}
        </div>
      )}

      {challengeFriend && (
        <ChallengeDialog
          friend={challengeFriend}
          onClose={() => setChallengeFriend(null)}
        />
      )}
    </div>
  );
}

function PresenceDot({ online }: { online: boolean }) {
  return (
    <span
      aria-label={online ? 'online' : 'offline'}
      className={['h-2.5 w-2.5 rounded-full', online ? 'bg-green' : 'bg-hairline'].join(
        ' ',
      )}
    />
  );
}

function FriendRow({
  friend,
  onChallenge,
}: {
  friend: FriendItem;
  onChallenge: (f: FriendItem) => void;
}) {
  const remove = useRemoveFriend();
  return (
    <ListRow
      left={<PresenceDot online={friend.online} />}
      title={friend.username ?? 'Player'}
      subline={friend.online ? 'Active now' : 'Offline'}
      right={
        <div className="flex items-center gap-2">
          <PillButton variant="secondary" onClick={() => onChallenge(friend)}>
            Challenge
          </PillButton>
          <PillButton
            variant="text"
            onClick={() => remove.mutate(friend.friendship_id)}
            disabled={remove.isPending}
          >
            Remove
          </PillButton>
        </div>
      }
    />
  );
}

function RequestRow({ friend }: { friend: FriendItem }) {
  const respond = useRespondFriend();
  return (
    <ListRow
      title={friend.username ?? 'Player'}
      subline="Wants to be friends"
      right={
        <div className="flex items-center gap-2">
          <PillButton
            onClick={() =>
              respond.mutate({ friendshipId: friend.friendship_id, action: 'accept' })
            }
            disabled={respond.isPending}
          >
            Accept
          </PillButton>
          <PillButton
            variant="text"
            onClick={() =>
              respond.mutate({ friendshipId: friend.friendship_id, action: 'decline' })
            }
            disabled={respond.isPending}
          >
            Decline
          </PillButton>
        </div>
      }
    />
  );
}
