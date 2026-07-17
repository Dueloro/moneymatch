import { formatCurrency } from '../../lib/format';
import { useReconciliation } from '../../hooks/useAdmin';
import { styles } from './adminStyles';

export function AdminReconciliationPage() {
  const recon = useReconciliation();
  if (recon.isLoading) return <div style={styles.page}>Running checks…</div>;
  const d = recon.data as
    | {
        ok: boolean;
        solvency_ok: boolean;
        solvency_violations: string[];
        totals: Record<string, number>;
        contest_violations: {
          ref_type: string;
          ref_id: string;
          violations: string[];
        }[];
        worker: { heartbeat_at: string | null; stale: boolean };
      }
    | undefined;
  if (!d) return null;

  return (
    <div style={styles.page}>
      <h1 style={styles.h1}>
        Reconciliation —{' '}
        <span style={d.ok ? styles.ok : styles.alert}>
          {d.ok ? 'OK' : 'VIOLATIONS'}
        </span>
      </h1>
      <p>
        Worker heartbeat:{' '}
        <span style={d.worker.stale ? styles.alert : styles.ok}>
          {d.worker.heartbeat_at ?? 'never'} {d.worker.stale ? '(STALE)' : '(fresh)'}
        </span>
      </p>
      <h1 style={{ ...styles.h1, marginTop: 12 }}>Global solvency</h1>
      <p style={d.solvency_ok ? styles.ok : styles.alert}>
        {d.solvency_ok ? 'solvent' : 'BREACH'}
      </p>
      <ul>
        <li>user total: {formatCurrency(d.totals.user_total ?? 0)}</li>
        <li>promo funding: {formatCurrency(d.totals.promo_funding ?? 0)}</li>
        <li>rake: {formatCurrency(d.totals.rake ?? 0)}</li>
      </ul>
      {d.solvency_violations.length > 0 && (
        <pre style={styles.pre}>{d.solvency_violations.join('\n')}</pre>
      )}

      <h1 style={{ ...styles.h1, marginTop: 12 }}>Per-contest conservation</h1>
      {d.contest_violations.length === 0 ? (
        <p style={styles.ok}>No contest breaches.</p>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Ref</th>
              <th style={styles.th}>Violations</th>
            </tr>
          </thead>
          <tbody>
            {d.contest_violations.map((v) => (
              <tr key={v.ref_id}>
                <td style={{ ...styles.td, ...styles.alert }}>
                  {v.ref_type} {v.ref_id.slice(0, 8)}
                </td>
                <td style={styles.td}>{v.violations.join('; ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
