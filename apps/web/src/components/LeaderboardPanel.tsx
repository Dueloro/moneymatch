import { formatRoi, useLeaderboard } from '../hooks/useLeaderboard';
import { EmptyState } from './ui/EmptyState';
import { ErrorState } from './ui/ErrorState';
import { SkeletonList } from './ui/Skeleton';
import { ListRow } from './ui/ListRow';

export function LeaderboardPanel() {
  const { data, isLoading, isError, refetch } = useLeaderboard();

  if (isLoading) return <SkeletonList rows={5} />;
  if (isError || !data) {
    return (
      <ErrorState
        title="Couldn't load the leaderboard"
        onRetry={() => void refetch()}
      />
    );
  }

  if (data.rows.length === 0) {
    return (
      <EmptyState
        title="Nobody is ranked yet"
        subline={`Finish ${data.min_contests} matches, pools or tournaments in ${data.window_days} days to get on the board.`}
      />
    );
  }

  return (
    <div>
      {data.rows.map((row) => (
        <ListRow
          key={row.user_id}
          left={
            <span className="w-6 text-sm tabular-nums text-text-secondary">
              {row.rank}
            </span>
          }
          title={
            <span className={row.is_you ? 'font-semibold text-text' : undefined}>
              {row.username ?? 'Player'}
              {row.is_you ? ' (you)' : ''}
            </span>
          }
          subline={`${row.contests} played`}
          right={
            <span className={row.roi_bps >= 0 ? 'text-green' : 'text-text-secondary'}>
              {formatRoi(row.roi_bps)}
            </span>
          }
        />
      ))}
      {!data.you.qualified && (
        <p className="mt-4 text-xs text-text-secondary">
          You are not ranked yet. Finish {data.you.contests_needed} more to qualify.
        </p>
      )}
    </div>
  );
}
