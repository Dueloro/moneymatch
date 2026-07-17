import { formatCurrency, formatPct } from '../../lib/format';
import { useClearFlag, useRisk } from '../../hooks/useAdmin';
import { styles } from './adminStyles';

export function AdminRiskPage() {
  const risk = useRisk();
  const clear = useClearFlag();
  if (risk.isLoading) return <div style={styles.page}>Loading…</div>;
  const d = risk.data as
    | {
        rates: {
          game: string;
          market: string;
          offered: number;
          accepted: number;
          settled: number;
          expected_rate: number | null;
          actual_rate: number | null;
          rake_cents: number;
          alert: boolean;
        }[];
        flags: {
          id: string;
          username: string | null;
          game: string;
          metric: string;
          kind: string;
        }[];
      }
    | undefined;
  if (!d) return null;

  return (
    <div style={styles.page}>
      <h1 style={styles.h1}>Rate drift</h1>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Game</th>
            <th style={styles.th}>Market</th>
            <th style={styles.th}>Offered</th>
            <th style={styles.th}>Accepted</th>
            <th style={styles.th}>Settled</th>
            <th style={styles.th}>Expected</th>
            <th style={styles.th}>Actual</th>
            <th style={styles.th}>Rake</th>
          </tr>
        </thead>
        <tbody>
          {d.rates.map((r, i) => (
            <tr key={i} style={r.alert ? { background: '#fdd' } : undefined}>
              <td style={styles.td}>{r.game}</td>
              <td style={styles.td}>
                {r.market}
                {r.alert && <span style={styles.alert}> ⚠</span>}
              </td>
              <td style={styles.td}>{r.offered}</td>
              <td style={styles.td}>{r.accepted}</td>
              <td style={styles.td}>{r.settled}</td>
              <td style={styles.td}>
                {r.expected_rate == null ? '—' : formatPct(r.expected_rate)}
              </td>
              <td style={styles.td}>
                {r.actual_rate == null ? '—' : formatPct(r.actual_rate)}
              </td>
              <td style={styles.td}>{formatCurrency(r.rake_cents)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h1 style={{ ...styles.h1, marginTop: 20 }}>Flag queue (sandbagging)</h1>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>User</th>
            <th style={styles.th}>Game</th>
            <th style={styles.th}>Metric</th>
            <th style={styles.th}>Kind</th>
            <th style={styles.th}></th>
          </tr>
        </thead>
        <tbody>
          {d.flags.map((f) => (
            <tr key={f.id}>
              <td style={styles.td}>{f.username ?? '—'}</td>
              <td style={styles.td}>{f.game}</td>
              <td style={styles.td}>{f.metric}</td>
              <td style={styles.td}>{f.kind}</td>
              <td style={styles.td}>
                <button style={styles.button} onClick={() => clear.mutate(f.id)}>
                  Clear
                </button>
              </td>
            </tr>
          ))}
          {d.flags.length === 0 && (
            <tr>
              <td style={styles.td} colSpan={5}>
                No open flags.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
