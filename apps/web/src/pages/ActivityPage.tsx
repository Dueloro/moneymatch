import { useMemo } from 'react';

import { Link } from 'react-router-dom';

import { ActivityCard } from '../components/activity/ActivityCard';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { PillButton } from '../components/ui/PillButton';
import { SectionHeader } from '../components/ui/SectionHeader';
import { usePageTitle } from '../hooks/usePageTitle';
import { SkeletonList } from '../components/ui/Skeleton';
import { useActivity } from '../hooks/useActivity';

export function ActivityPage() {
  usePageTitle('Activity');
  const { data, isLoading, isError, refetch } = useActivity();
  const items = useMemo(() => data?.items ?? [], [data]);

  const newestFinished = items.find((i) => i.resolved_at != null);

  return (
    <div>
      <SectionHeader
        level="page"
        hint="Your matches, pools and tournaments, newest first."
      >
        Activity
      </SectionHeader>

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
          title="Nothing played yet"
          subline="Your results land here automatically after each game."
          action={
            <Link to="/play">
              <PillButton>Start playing</PillButton>
            </Link>
          }
        />
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((item) => (
            <ActivityCard
              key={item.id}
              item={item}
              defaultOpen={item.id === newestFinished?.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
