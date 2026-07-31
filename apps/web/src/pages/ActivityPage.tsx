import { useEffect, useMemo, useRef } from 'react';

import { ActivityCard } from '../components/activity/ActivityCard';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { SkeletonList } from '../components/ui/Skeleton';
import { formatCurrency } from '../lib/format';
import { toast } from '../lib/toast';
import { useActivity, type ActivityItem } from '../hooks/useActivity';

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
        <div className="flex flex-col gap-2">
          {items.map((item) => (
            <ActivityCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
