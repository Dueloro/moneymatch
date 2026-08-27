import { Link } from 'react-router-dom';

import { useActivity, type ActivityItem } from '../../hooks/useActivity';
import { useLeavePool, usePoolStatus } from '../../hooks/usePools';
import { useLeaveTournament, useTournamentStatus } from '../../hooks/useTournaments';
import { useWallet } from '../../hooks/useWallet';
import { formatCurrency } from '../../lib/format';
import { gameMeta } from '../../lib/games';
import { LiveLine } from '../activity/LiveLine';
import { AnimatedBalance } from '../ui/AnimatedBalance';
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
 * open the app for: what they have and what they have running right now.
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
/** You are in a queue and nothing has formed yet. */
function QueuingCard({
  label,
  hint,
  onCancel,
  cancelling,
  testId,
}: {
  label: string;
  hint: string;
  onCancel?: () => void;
  cancelling?: boolean;
  testId: string;
}) {
  return (
    <Card className="p-3" data-testid={testId}>
      <div className="flex items-center gap-2">
        <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-live" />
        <p className="text-sm font-medium text-text">{label}</p>
      </div>
      <p className="mt-1 text-xs text-text-secondary">{hint}</p>
      {onCancel && (
        <PillButton
          className="mt-2 px-0"
          size="sm"
          variant="text"
          onClick={onCancel}
          disabled={cancelling}
        >
          Cancel
        </PillButton>
      )}
    </Card>
  );
}

/** The pool you are actually in, once a room has formed. */
function RoomFormed() {
  const { data: status } = usePoolStatus();

  const pool = status?.status === 'formed' ? status.pool : null;
  if (!pool) return null;

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
  const { data: poolStatus } = usePoolStatus();
  const { data: tournamentStatus } = useTournamentStatus();
  const leavePool = useLeavePool();
  const leaveTournament = useLeaveTournament();

  const available = wallet?.available_cents ?? 0;
  const inPlayCents = wallet?.escrow_cents ?? 0;

  const searchingPool = poolStatus?.status === 'searching';
  const searchingTournament = tournamentStatus?.status === 'searching';
  const queuing = searchingPool || searchingTournament;
  const formedPool = poolStatus?.status === 'formed' ? poolStatus.pool : null;

  // A formed pool is also an OPEN/LOCKED row in the activity feed, so it would
  // otherwise render twice: once as the rich room card, once as a generic
  // in-play card. The room card wins (it carries the bar and the play cue).
  const inPlay = (activity?.items ?? [])
    .filter((i) => IN_PLAY.has(i.state) && i.id !== formedPool?.id)
    .slice(0, 3);

  const nothingRunning = !formedPool && inPlay.length === 0;

  return (
    <div className="flex flex-col gap-6">
      {showBalance && (
        <Card className="mm-grid-surface p-4">
          <p className="label-money">Balance</p>
          <p className="mt-1 text-3xl font-semibold text-green">
            <AnimatedBalance cents={available} testId="rail-balance" />
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

      {/* Two states, two labels. Waiting for a room is not the same as being in
       * one, and calling both "In play" left you unable to tell whether you
       * were still matching or already playing. A contest appears under
       * Queuing, then moves to In play the moment it forms. */}
      {queuing && (
        <RailSection title="Queuing">
          <div className="flex flex-col gap-2">
            {searchingPool && (
              <QueuingCard
                testId="rail-pool-status"
                label="Finding your pool room"
                hint="Matching you with players of a similar standard."
                onCancel={() => leavePool.mutate()}
                cancelling={leavePool.isPending}
              />
            )}
            {searchingTournament && (
              <QueuingCard
                testId="rail-tournament-status"
                label="Finding your tournament field"
                hint="Matching you with players of a similar standard."
                onCancel={() => leaveTournament.mutate()}
                cancelling={leaveTournament.isPending}
              />
            )}
          </div>
        </RailSection>
      )}

      <RailSection title="In play" action={{ to: '/activity', label: 'All' }}>
        {nothingRunning ? (
          <p className="text-xs text-text-tertiary">
            {queuing
              ? 'Nothing running yet. Your contest lands here once it forms.'
              : 'Nothing running. Join a pool to get started.'}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {formedPool && <RoomFormed />}
            {inPlay.map((item) => (
              <InPlayCard key={item.id} item={item} />
            ))}
          </div>
        )}
      </RailSection>
    </div>
  );
}
