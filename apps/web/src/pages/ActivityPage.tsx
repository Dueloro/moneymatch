import { useEffect, useMemo, useRef } from 'react';

import { Link } from 'react-router-dom';

import { ActivityCard } from '../components/activity/ActivityCard';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { PillButton } from '../components/ui/PillButton';
import { AutoCollectCard } from '../components/cs2/AutoCollectCard';
import { SubmitMatchCard } from '../components/cs2/SubmitMatchCard';
import { useLinks } from '../hooks/useLinks';
import { SectionHeader } from '../components/ui/SectionHeader';
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

  // Steam is what ties a submitted match to you, so the card asks for
  // sign-in first rather than failing on submit.
  const { data: links } = useLinks();
  const cs2Linked =
    links?.games.some((g) => g.game === 'cs2.steam' && g.status === 'LINKED') ?? false;

  // The newest contest that has actually finished. `items` is newest first, so
  // the first resolved row is the one you just played.
  const newestFinished = items.find((i) => i.resolved_at != null);

  return (
    // Spans the column rather than capping at the reading measure: the rail
    // already balances the page, so a 640px cap only stranded ~160px of dead
    // column between the list and the rail.
    <div>
      <SectionHeader level="page" hint="Every contest you have played, newest first.">
        Activity
      </SectionHeader>

      {/* CS2 has no public per-match stats API, so a played match only becomes
       * a settled wager once its share code is pasted. This is the place you
       * land after playing, so it is the place to ask for it. */}
      <div className="mb-6">
        <SubmitMatchCard linked={cs2Linked} />
          <AutoCollectCard linked={cs2Linked} />
      </div>

      {isError ? (
        <ErrorState
          title="Could not load your activity"
          subline="The connection dropped. Try again."
          onRetry={() => refetch()}
        />
      ) : isLoading ? (
        <SkeletonList rows={5} />
      ) : items.length === 0 ? (
        <EmptyState
          title="No contests yet"
          subline="Join a pool and your results land here automatically."
          action={
            <Link to="/pools">
              <PillButton>Browse solo pools</PillButton>
            </Link>
          }
        />
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((item) => (
            <ActivityCard
              key={item.id}
              item={item}
              // Your latest finished contest opens on arrival, so the stat line
              // you actually came to check is on screen without a click. Every
              // older row stays collapsed.
              defaultOpen={item.id === newestFinished?.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
