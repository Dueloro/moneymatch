import { Link } from 'react-router-dom';

import { useActivity, type ActivityItem } from '../../hooks/useActivity';
import { useDisplayBalance } from '../../hooks/useDisplayBalance';
import { useLeavePool, usePoolStatus } from '../../hooks/usePools';
import { useLeaveTournament, useTournamentStatus } from '../../hooks/useTournaments';
import { useWallet } from '../../hooks/useWallet';
import { formatCurrency } from '../../lib/format';
import { barPhrase, isLowerBetter } from '../../lib/metrics';
import { LiveLine } from '../activity/LiveLine';
import { AnimatedBalance } from '../ui/AnimatedBalance';
import { Card } from '../ui/Card';
import { ClearBar } from '../ui/ClearBar';
import { PillButton } from '../ui/PillButton';
import { SectionHeader } from '../ui/SectionHeader';

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
        <p className="shrink-0 text-xs tabular-nums text-text-tertiary">
          {formatCurrency(item.entry_cents)}
        </p>
      </div>
      <p className="mt-0.5 truncate text-xs text-text-secondary">{item.market_label}</p>
      {pool ? (
        <div className="mt-3">
          <ClearBar
            size="sm"
            current={pool.current}
            target={pool.target}
            label={live?.label ?? 'you'}
            lowerIsBetter={isLowerBetter(item.market)}
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
      </div>
      <p className="mt-0.5 text-xs text-text-secondary">
        {pool.room_size} {pool.room_size === 1 ? 'player' : 'players'} · pot{' '}
        {formatCurrency(pool.pot_cents)}
      </p>
      <div className="mt-3">
        <ClearBar
          size="sm"
          current={pool.your_bar}
          target={pool.room_bar}
          lowerIsBetter={isLowerBetter(pool.metric)}
        />
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
          . Play again to {barPhrase(pool.metric, pool.room_bar)}.
        </p>
      ) : (
        <p className="mt-3 text-xs text-text" data-testid="rail-room-play-cue">
          Your {formatCurrency(pool.entry_cents)} is in escrow. Play your next game on
          Lichess.
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

  const available = useDisplayBalance();
  const inPlayCents = wallet?.escrow_cents ?? 0;

  const searchingPool = poolStatus?.status === 'searching';
  const searchingTournament = tournamentStatus?.status === 'searching';
  const queuing = searchingPool || searchingTournament;
  const formedPool = poolStatus?.status === 'formed' ? poolStatus.pool : null;

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
