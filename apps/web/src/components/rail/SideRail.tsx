import { Link } from 'react-router-dom';

import { useActivity, type ActivityItem } from '../../hooks/useActivity';
import { useWaiting } from '../../hooks/useMatchmaking';
import { useLeavePool, usePoolStatus } from '../../hooks/usePools';
import { useWallet } from '../../hooks/useWallet';
import { formatCurrency } from '../../lib/format';
import { gameMeta } from '../../lib/games';
import { LiveLine } from '../activity/LiveLine';
import { Card } from '../ui/Card';
import { ClearBar } from '../ui/ClearBar';
import { GameBadge } from '../ui/GameBadge';
import { PillButton } from '../ui/PillButton';
import { SectionHeader } from '../ui/SectionHeader';

/**
 * The persistent right rail (16-ui-revamp-plan §5).
 *
 * The inventory found roughly 60% of a 1920px viewport empty on the browse
 * pages, with a 576px column stranded mid-screen on Friends. The fix is not
 * wider cards, it is giving a returning player the four things they actually
 * open the app for: what they have, what they have in play, who is queuing, and
 * the room they are sitting in.
 *
 * Every number here comes from a hook that already exists. The in-play list
 * reads `useActivity` (one 10s poll, already the Activity page's source) rather
 * than the three per-mode status endpoints, so mounting the rail app-wide costs
 * one request, not three at 2.5s.
 */

const IN_PLAY = new Set(['PENDING', 'ACTIVE', 'AWAITING_RESULT', 'OPEN', 'LOCKED']);

function RailSection({
  title,
  action,
  children,
}: {
  title: string;
  action?: { to: string; label: string };
  children: React.ReactNode;
}) {
  return (
    <section>
      <SectionHeader
        level="sub"
        action={
          action && (
            <Link
              to={action.to}
              className="text-xs text-text-secondary transition-colors hover:text-text"
            >
              {action.label}
            </Link>
          )
        }
      >
        {title}
      </SectionHeader>
      {children}
    </section>
  );
}

function title(item: ActivityItem): string {
  if (item.title) return item.title;
  return `vs ${item.opponent_username ?? 'opponent'}`;
}

/** One in-flight contest. A pool shows the clear bar, because the bar is the
 * whole contest; everything else shows its live line. */
function InPlayCard({ item }: { item: ActivityItem }) {
  const live = item.live;
  const pool =
    live && live.kind === 'pool' && typeof live.target === 'number'
      ? {
          current: typeof live.current === 'number' ? live.current : null,
          target: live.target,
        }
      : null;

  return (
    <Card className="p-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="truncate text-sm font-medium text-text">{title(item)}</p>
        <p className="shrink-0 text-xs text-text-tertiary">
          {formatCurrency(item.entry_cents)}
        </p>
      </div>
      <div className="mt-0.5 flex items-center gap-1.5">
        <GameBadge game={item.game} />
        <span className="truncate text-xs text-text-secondary">
          {item.market_label}
        </span>
      </div>
      {pool ? (
        <div className="mt-3">
          <ClearBar
            size="sm"
            current={pool.current}
            target={pool.target}
            label={live?.label ?? 'you'}
          />
        </div>
      ) : (
        live && (
          <div className="mt-2">
            <LiveLine live={live} />
          </div>
        )
      )}
    </Card>
  );
}

/**
 * The pool you have in flight. It sits in the rail rather than above the browse
 * grid so a formed room stops pushing the cards you are still reading down the
 * page. PoolsPage keeps a copy inline below `xl`, where there is no rail.
 */
function RoomFormed() {
  const { data: status } = usePoolStatus();
  const leave = useLeavePool();

  if (status?.status === 'searching') {
    return (
      <Card className="p-3" data-testid="rail-pool-status">
        <div className="flex items-center gap-2">
          <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-live" />
          <p className="text-sm font-medium text-text">Finding your room</p>
        </div>
        <p className="mt-1 text-xs text-text-secondary">
          Matching you with players of a similar standard.
        </p>
        <PillButton
          className="mt-2 px-0"
          size="sm"
          variant="text"
          onClick={() => leave.mutate()}
          disabled={leave.isPending}
        >
          Cancel
        </PillButton>
      </Card>
    );
  }

  const pool = status?.status === 'formed' ? status.pool : null;
  if (!pool) {
    return (
      <p className="text-xs text-text-tertiary">
        No room yet. Join a pool and it lands here.
      </p>
    );
  }

  return (
    <Card className="p-3" data-testid="rail-room-card">
      <div className="flex items-center gap-2">
        <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-live" />
        <p className="min-w-0 flex-1 truncate text-sm font-medium capitalize text-text">
          {pool.difficulty} {pool.metric_label}
        </p>
        <GameBadge game={pool.game} />
      </div>
      <p className="mt-0.5 text-xs text-text-secondary">
        {pool.room_size} {pool.room_size === 1 ? 'player' : 'players'} · pot{' '}
        {formatCurrency(pool.pot_cents)}
      </p>
      <div className="mt-3">
        <ClearBar size="sm" current={pool.your_bar} target={pool.room_bar} />
      </div>
      <p className="mt-1 text-xs text-text-tertiary">Room bar {pool.room_bar}</p>
      {pool.your_cleared === true ? (
        <p className="mt-3 text-xs font-medium text-green" data-testid="rail-room-live">
          Cleared ✓
          {pool.your_current != null && (
            <span className="text-text-secondary">
              {' '}
              · your {pool.metric_label} {pool.your_current}
            </span>
          )}{' '}
          · settling now.
        </p>
      ) : pool.your_cleared === false ? (
        <p className="mt-3 text-xs text-text" data-testid="rail-room-live">
          Not over the bar yet
          {pool.your_current != null && (
            <span className="text-text-secondary">
              {' '}
              · your {pool.metric_label} {pool.your_current}
            </span>
          )}
          . Play again to beat {pool.room_bar}.
        </p>
      ) : (
        <p className="mt-3 text-xs text-text" data-testid="rail-room-play-cue">
          Your {formatCurrency(pool.entry_cents)} is in escrow, so you can now play your{' '}
          {gameMeta(pool.game).name} game.
        </p>
      )}
    </Card>
  );
}

export function SideRail({ showBalance = true }: { showBalance?: boolean }) {
  const { data: wallet } = useWallet();
  const { data: activity } = useActivity();
  const { data: waitingData } = useWaiting(undefined);

  const available = wallet?.available_cents ?? 0;
  const inPlayCents = wallet?.escrow_cents ?? 0;

  const inPlay = (activity?.items ?? [])
    .filter((i) => IN_PLAY.has(i.state))
    .slice(0, 3);
  const waiting = (waitingData?.waiting ?? []).slice(0, 4);

  return (
    <div className="flex flex-col gap-6">
      {showBalance && (
        <Card className="p-4">
          <p className="label-money">Balance</p>
          <p className="mt-1 text-3xl font-semibold text-green">
            {formatCurrency(available)}
          </p>
          {inPlayCents > 0 && (
            <p className="mt-1 text-xs text-text-secondary">
              {formatCurrency(inPlayCents)} in play
            </p>
          )}
          <Link
            to="/wallet"
            className="mt-3 inline-block text-xs font-semibold text-text-secondary transition-colors hover:text-text"
          >
            Add funds
          </Link>
        </Card>
      )}

      <RailSection title="In play" action={{ to: '/activity', label: 'All' }}>
        {inPlay.length === 0 ? (
          <p className="text-xs text-text-tertiary">
            Nothing running. Join a pool to get started.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {inPlay.map((item) => (
              <InPlayCard key={item.id} item={item} />
            ))}
          </div>
        )}
      </RailSection>

      <RailSection title="Queue" action={{ to: '/play', label: 'Play' }}>
        {waiting.length === 0 ? (
          <p className="text-xs text-text-tertiary">Nobody waiting right now.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {waiting.map((w) => (
              <li
                key={w.ticket_id}
                className="flex items-baseline justify-between gap-2 text-xs"
              >
                <span className="flex min-w-0 items-baseline gap-2">
                  <span
                    aria-hidden
                    className="h-1.5 w-1.5 shrink-0 translate-y-[-1px] rounded-full bg-live"
                  />
                  <span className="truncate font-medium text-text">
                    {w.username ?? 'A player'}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1.5">
                  <GameBadge game={w.game} />
                  <span className="text-text-tertiary">
                    {formatCurrency(w.entry_cents)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </RailSection>

      <RailSection title="Room formed" action={{ to: '/pools', label: 'Pools' }}>
        <RoomFormed />
      </RailSection>
    </div>
  );
}
