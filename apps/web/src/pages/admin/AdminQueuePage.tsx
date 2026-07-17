import { formatCurrency, formatPct } from '../../lib/format';
import { useAdminQueue } from '../../hooks/useAdmin';
import { styles } from './adminStyles';

export function AdminQueuePage() {
  const queue = useAdminQueue();
  if (queue.isLoading) return <div style={styles.page}>Loading…</div>;
  const d = queue.data as
    | {
        waiting: number;
        matched: number;
        expired: number;
        canceled: number;
        expiry_rate: number;
        depth: {
          game: string;
          market: string;
          entry_cents: number;
          waiting: number;
          avg_wait_seconds: number;
        }[];
      }
    | undefined;
  if (!d) return null;

  return (
    <div style={styles.page}>
      <h1 style={styles.h1}>Queue (live, refreshes every 5s)</h1>
      <p>
        waiting {d.waiting} · matched {d.matched} · expired {d.expired} · canceled{' '}
        {d.canceled} · expiry rate {formatPct(d.expiry_rate)}
      </p>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Game</th>
            <th style={styles.th}>Market</th>
            <th style={styles.th}>Tier</th>
            <th style={styles.th}>Waiting</th>
            <th style={styles.th}>Avg wait</th>
          </tr>
        </thead>
        <tbody>
          {d.depth.map((row, i) => (
            <tr key={i}>
              <td style={styles.td}>{row.game}</td>
              <td style={styles.td}>{row.market}</td>
              <td style={styles.td}>{formatCurrency(row.entry_cents)}</td>
              <td style={styles.td}>{row.waiting}</td>
              <td style={styles.td}>{Math.round(row.avg_wait_seconds)}s</td>
            </tr>
          ))}
          {d.depth.length === 0 && (
            <tr>
              <td style={styles.td} colSpan={5}>
                Queue empty.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
