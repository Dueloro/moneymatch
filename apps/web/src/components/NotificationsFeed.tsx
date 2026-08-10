import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  useMarkNotificationsRead,
  useNotifications,
  type NotificationItem,
} from '../hooks/useNotifications';
import { formatRelativeTime } from '../lib/format';
import { PoolDetail, TournamentDetail } from './notifications/ContestDetail';
import { EmptyState } from './ui/EmptyState';
import { ExpandableCard } from './ui/ExpandableCard';
import { PillButton } from './ui/PillButton';
import { useAcceptChallenge, useDeclineChallenge } from '../hooks/useChallenges';

/** The notification feed (design p.11): rows with an unread dot, age, and action
 * pills (View → deep link; Respond → accept/decline a challenge). Mark-read on
 * view. It lives inside the Inbox, as the pinned "Notifications" thread of the
 * messaging surface. */
export function NotificationsFeed() {
  const { data } = useNotifications();
  const markRead = useMarkNotificationsRead();

  // Mark everything read once, when there's something unread (design: on view).
  useEffect(() => {
    if (data && data.unread > 0) markRead.mutate(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.unread]);

  return (
    <div className="max-w-xl">
      {data && data.items.length === 0 ? (
        <EmptyState title="No notifications" subline="You're all caught up." />
      ) : (
        <div className="flex flex-col gap-2">
          {data?.items.map((n) => (
            <NotificationRow key={n.id} note={n} />
          ))}
        </div>
      )}
    </div>
  );
}

function describe(note: NotificationItem): string {
  const p = note.payload;
  const name = (p.from_username as string) || (p.by_username as string) || 'Someone';
  switch (note.kind) {
    case 'challenge_received':
      return `${name} challenged you${p.friendly ? ' (friendly)' : ''}`;
    case 'challenge_accepted':
      return `${name} accepted your challenge`;
    case 'friend_request':
      return p.status === 'accepted'
        ? `${name} accepted your friend request`
        : `${name} sent you a friend request`;
    case 'match_found':
      return 'You have a match. Confirm to play';
    case 'room_filled':
      return 'Your pool room filled';
    case 'settled':
      return 'A contest settled';
    case 'refund':
      return 'A contest was refunded';
    case 'system':
      if (p.event === 'challenge_declined') return 'Your challenge was declined';
      if (p.event === 'challenge_expired') return 'Your challenge expired';
      return 'Update';
    default:
      return 'Update';
  }
}

function NotificationRow({ note }: { note: NotificationItem }) {
  const navigate = useNavigate();
  const accept = useAcceptChallenge();
  const decline = useDeclineChallenge();
  const p = note.payload;

  const challengeId =
    note.kind === 'challenge_received' ? (p.challenge_id as string) : null;
  const matchId =
    (note.kind === 'match_found' || note.kind === 'challenge_accepted') &&
    (p.match_id as string | undefined)
      ? (p.match_id as string)
      : null;

  // A contest notification carries the id of the thing it is about, so the row
  // can open into the room itself: who is in it, and once it settles, what
  // everyone did. Anything else stays a plain row.
  const poolId = p.kind === 'pool' ? ((p.pool_id as string) ?? null) : null;
  const tournamentId =
    p.kind === 'tournament' ? ((p.tournament_id as string) ?? null) : null;

  async function onAccept() {
    if (!challengeId) return;
    const res = await accept.mutateAsync(challengeId);
    navigate(`/play?match=${res.match_id}`);
  }

  return (
    <ExpandableCard
      ariaLabel={
        poolId || tournamentId ? `${describe(note)}, open for detail` : undefined
      }
      left={
        <span
          aria-label={note.read ? 'read' : 'unread'}
          className={[
            'h-2 w-2 rounded-full',
            note.read ? 'bg-transparent' : 'bg-action',
          ].join(' ')}
        />
      }
      title={describe(note)}
      subline={formatRelativeTime(note.created_at)}
      right={
        challengeId ? (
          <div className="flex items-center gap-2">
            <PillButton onClick={onAccept} disabled={accept.isPending}>
              Respond
            </PillButton>
            <PillButton
              variant="text"
              onClick={() => decline.mutate(challengeId)}
              disabled={decline.isPending}
            >
              Decline
            </PillButton>
          </div>
        ) : matchId ? (
          <PillButton
            variant="outline"
            onClick={() => navigate(`/play?match=${matchId}`)}
          >
            View
          </PillButton>
        ) : undefined
      }
    >
      {poolId ? (
        <PoolDetail poolId={poolId} />
      ) : tournamentId ? (
        <TournamentDetail tournamentId={tournamentId} />
      ) : undefined}
    </ExpandableCard>
  );
}
