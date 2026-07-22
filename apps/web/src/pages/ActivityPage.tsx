import { useEffect, useMemo, useRef } from 'react';

import { AmountText } from '../components/ui/AmountText';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { ListRow } from '../components/ui/ListRow';
import { PillButton } from '../components/ui/PillButton';
import { SkeletonList } from '../components/ui/Skeleton';
import { formatCurrency, formatRelativeTime } from '../lib/format';
import { toast } from '../lib/toast';
import { statValue, useActivity, type ActivityItem } from '../hooks/useActivity';
import { useCreateChallenge } from '../hooks/useChallenges';

const LIVE_STATES = new Set(['ACTIVE', 'AWAITING_RESULT']);
const TERMINAL_STATES = new Set(['SETTLED', 'PUSHED', 'CANCELED']);

/** A win or a live contest gets the green dot; everything settled is gray. */
function dotClass(item: ActivityItem): string {
  const won = item.state === 'SETTLED' && (item.net_cents ?? 0) > 0;
  const live = LIVE_STATES.has(item.state) || item.state === 'LOCKED';
  return won || live ? 'bg-green' : 'bg-text-secondary';
}

function stateLabel(item: ActivityItem): string {
  switch (item.state) {
    case 'PENDING':
      return 'Awaiting confirmation';
    case 'ACTIVE':
    case 'AWAITING_RESULT':
    case 'OPEN':
    case 'LOCKED':
      return 'In progress';
    case 'PUSHED':
      return 'Push · refunded';
    case 'CANCELED':
      return 'Refunded';
    case 'SETTLED':
      if ((item.net_cents ?? 0) > 0) return 'Won';
      return (item.net_cents ?? 0) < 0 ? 'Lost' : 'Settled';
    default:
      return item.state;
  }
}

/** Stat-race result line (matches only — pools/tournaments have no opponent). */
function statLine(item: ActivityItem): string | null {
  if (item.type !== 'match') return null;
  const you = statValue(item.your_stat_line);
  const opp = statValue(item.opponent_stat_line);
  if (you == null && opp == null) return null;
  const name = item.opponent_username ?? 'opponent';
  return `You ${you ?? '—'} · ${name} ${opp ?? '—'}`;
}

function title(item: ActivityItem): string {
  if (item.title) return item.title;
  return `vs ${item.opponent_username ?? 'opponent'} · ${item.market_label}`;
}

/** A newly-settled contest → a one-line toast summarizing the outcome. */
function toastFor(item: ActivityItem): string {
  const what =
    item.type === 'match'
      ? `vs ${item.opponent_username ?? 'opponent'}`
      : (item.title ?? item.market_label);
  const net = item.net_cents ?? 0;
  if (item.state === 'SETTLED') {
    if (net > 0) return `You won ${formatCurrency(net)} ${what}`;
    if (net < 0) return `You lost ${formatCurrency(Math.abs(net))} ${what}`;
    return `Settled · ${what}`;
  }
  if (item.state === 'PUSHED') return `Push ${what} · entry refunded`;
  return `Refunded · ${what}`;
}

/** One-tap rematch on a settled H2H row → challenge the same opponent
 * (08-phase-5 · deliverable 6). */
function RematchButton({ item }: { item: ActivityItem }) {
  const rematch = useCreateChallenge();
  if (item.type !== 'match' || !TERMINAL_STATES.has(item.state)) return null;
  return (
    <PillButton
      variant="outline"
      disabled={rematch.isPending}
      onClick={async () => {
        try {
          await rematch.mutateAsync({ rematch_of: item.id });
          toast.success(`Rematch sent to ${item.opponent_username ?? 'opponent'}`);
        } catch {
          // The failure is surfaced by the global mutation-error toast.
        }
      }}
    >
      Rematch
    </PillButton>
  );
}

export function ActivityPage() {
  const { data, isLoading, isError, refetch } = useActivity();
  const items = useMemo(() => data?.items ?? [], [data]);

  // Settlement toast: track which resolved matches we've already shown, seeding
  // from the first load so we only pop for transitions that happen live.
  const seen = useRef<Set<string> | null>(null);

  useEffect(() => {
    const resolved = items.filter((i) => i.resolved_at != null);
    if (seen.current === null) {
      seen.current = new Set(resolved.map((i) => i.id));
      return;
    }
    const fresh = resolved.find((i) => !seen.current!.has(i.id));
    if (fresh) {
      resolved.forEach((i) => seen.current!.add(i.id));
      toast.info(toastFor(fresh));
    }
  }, [items]);

  return (
    <div className="max-w-2xl">
      <h1 className="mb-6 text-2xl font-bold">Activity</h1>

      {isError ? (
        <ErrorState title="Could not load your activity" onRetry={() => refetch()} />
      ) : isLoading ? (
        <SkeletonList rows={5} />
      ) : items.length === 0 ? (
        <EmptyState
          title="Nothing here yet"
          subline="Your matches, pools, and tournaments will show up here."
        />
      ) : (
        <div>
          {items.map((item) => {
            const sub = statLine(item);
            return (
              <ListRow
                key={item.id}
                left={
                  <span
                    aria-hidden
                    className={`h-2.5 w-2.5 rounded-full ${dotClass(item)}`}
                  />
                }
                title={title(item)}
                subline={
                  <>
                    {stateLabel(item)}
                    {sub && <span className="text-text-secondary"> · {sub}</span>}
                    {item.resolved_at && (
                      <span className="text-text-secondary">
                        {' '}
                        · {formatRelativeTime(item.resolved_at)}
                      </span>
                    )}
                  </>
                }
                right={
                  <div className="flex items-center gap-3">
                    {item.net_cents != null ? (
                      <AmountText cents={item.net_cents} win={item.net_cents > 0} />
                    ) : (
                      <span className="text-xs text-text-secondary">
                        {formatCurrency(item.entry_cents)} in play
                      </span>
                    )}
                    <RematchButton item={item} />
                  </div>
                }
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
