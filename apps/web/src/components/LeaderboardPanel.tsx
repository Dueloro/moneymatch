import { formatRoi, useLeaderboard } from '../hooks/useLeaderboard';
import { EmptyState } from './ui/EmptyState';
import { ListRow } from './ui/ListRow';

/** Leaderboard tab (design p.7): ROI-ranked real users, you-row highlighted. */
export function LeaderboardPanel() {
  const { data } = useLeaderboard();

  if (!data) return null;

  if (data.rows.length === 0) {
    return (
      <EmptyState
        title="No ranked players yet"
        subline={`Play ${data.min_contests}+ settled contests over ${data.window_days} days to make the board.`}
      />
    );
  }

  return (
    <div className="max-w-xl">
      {data.rows.map((row) => (
        <ListRow
          key={row.user_id}
          left={
            <span className="w-6 text-sm tabular-nums text-text-secondary">
              {row.rank}
            </span>
          }
          title={
            <span className={row.is_you ? 'font-semibold text-green' : undefined}>
              {row.username ?? 'Player'}
              {row.is_you ? ' (you)' : ''}
            </span>
          }
          subline={`${row.contests} contests`}
          right={
            <span
              className={[
                'tabular-nums',
                row.roi_bps >= 0 ? 'text-green' : 'text-text-secondary',
              ].join(' ')}
            >
              {formatRoi(row.roi_bps)}
            </span>
          }
        />
      ))}
      {!data.you.qualified && (
        <p className="mt-4 text-xs text-text-secondary">
          You&apos;re not ranked yet — play {data.you.contests_needed} more settled
          contest{data.you.contests_needed === 1 ? '' : 's'} to qualify.
        </p>
      )}
    </div>
  );
}
