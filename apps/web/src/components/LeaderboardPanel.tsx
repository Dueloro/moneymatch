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
        title="Nobody is ranked yet"
        subline={`Settle ${data.min_contests} contests inside ${data.window_days} days and you are on the board.`}
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
          subline={`${row.contests} contests`}
          right={
            // ROI is a return on money, so lime stays correct here.
            <span className={row.roi_bps >= 0 ? 'text-green' : 'text-text-secondary'}>
              {formatRoi(row.roi_bps)}
            </span>
          }
        />
      ))}
      {!data.you.qualified && (
        <p className="mt-4 text-xs text-text-secondary">
          You are not ranked yet. Settle {data.you.contests_needed} more contest
          {data.you.contests_needed === 1 ? '' : 's'} to qualify.
        </p>
      )}
    </div>
  );
}
