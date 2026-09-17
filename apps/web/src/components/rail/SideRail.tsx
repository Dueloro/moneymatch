import { Link } from 'react-router-dom';

import { useActivity, type ActivityItem } from '../../hooks/useActivity';
import { useDisplayBalance } from '../../hooks/useDisplayBalance';
import { useLeaveTournament, useTournamentStatus } from '../../hooks/useTournaments';
import { useWallet } from '../../hooks/useWallet';
import { formatCurrency } from '../../lib/format';
import { LiveLine } from '../activity/LiveLine';
import { AnimatedBalance } from '../ui/AnimatedBalance';
import { Card } from '../ui/Card';
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
 * than the per-mode status endpoints, so mounting the rail app-wide costs one
 * request, not several.
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

/** One in-flight contest, showing its live line. */
function InPlayCard({ item }: { item: ActivityItem }) {
  const live = item.live;
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
      {live && (
        <div className="mt-2">
          <LiveLine live={live} />
        </div>
      )}
    </Card>
  );
}

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

export function SideRail({ showBalance = true }: { showBalance?: boolean }) {
  const { data: wallet } = useWallet();
  const { data: activity } = useActivity();
  const { data: tournamentStatus } = useTournamentStatus();
  const leaveTournament = useLeaveTournament();

  // Undefined (not `?? 0`) while loading, so AnimatedBalance shows a placeholder
  // rather than flashing $0 and firing a phantom gain on refresh. Held at its
  // pre-settlement value while a win/loss overlay is up (see useDisplayBalance).
  const available = useDisplayBalance();
  const inPlayCents = wallet?.escrow_cents ?? 0;

  const queuing = tournamentStatus?.status === 'searching';

  const inPlay = (activity?.items ?? [])
    .filter((i) => IN_PLAY.has(i.state))
    .slice(0, 3);

  const nothingRunning = inPlay.length === 0;

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

      {/* Two states, two labels. Waiting for a field is not the same as being in
       * one, and calling both "In play" left you unable to tell whether you
       * were still matching or already playing. A contest appears under
       * Queuing, then moves to In play the moment it forms. */}
      {queuing && (
        <RailSection title="Queuing">
          <div className="flex flex-col gap-2">
            <QueuingCard
              testId="rail-tournament-status"
              label="Finding your tournament field"
              hint="Matching you with players of a similar standard."
              onCancel={() => leaveTournament.mutate()}
              cancelling={leaveTournament.isPending}
            />
          </div>
        </RailSection>
      )}

      <RailSection title="In play" action={{ to: '/activity', label: 'All' }}>
        {nothingRunning ? (
          <p className="text-xs text-text-tertiary">
            {queuing
              ? 'Nothing running yet. Your contest lands here once it forms.'
              : 'Nothing running. Join a tournament to get started.'}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {inPlay.map((item) => (
              <InPlayCard key={item.id} item={item} />
            ))}
          </div>
        )}
      </RailSection>
    </div>
  );
}
