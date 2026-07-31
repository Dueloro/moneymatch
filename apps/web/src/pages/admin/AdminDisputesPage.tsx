import { useState } from 'react';

import { useAdminDisputes, useResolveDispute } from '../../hooks/useAdmin';
import { styles } from './adminStyles';

export function AdminDisputesPage() {
  const disputes = useAdminDisputes();
  const resolve = useResolveDispute();
  const [notes, setNotes] = useState<Record<string, string>>({});

  const act = (id: string, status: 'resolved' | 'rejected') =>
    resolve.mutate({ dispute_id: id, status, note: notes[id] });

  return (
    <div style={styles.page}>
      <h1 style={styles.h1}>Disputes</h1>
      {disputes.isError && <p style={styles.alert}>Failed to load disputes.</p>}
      {disputes.data && disputes.data.length === 0 && (
        <p style={styles.ok}>No open disputes.</p>
      )}
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Filed</th>
            <th style={styles.th}>Type</th>
            <th style={styles.th}>Contest</th>
            <th style={styles.th}>User</th>
            <th style={styles.th}>Reason</th>
            <th style={styles.th}>Note → user</th>
            <th style={styles.th}></th>
          </tr>
        </thead>
        <tbody>
          {(disputes.data ?? []).map((d) => (
            <tr key={d.id}>
              <td style={styles.td}>{new Date(d.created_at).toLocaleString()}</td>
              <td style={styles.td}>{d.ref_type}</td>
              <td style={styles.td} title={d.ref_id}>
                {d.ref_id.slice(0, 8)}…
              </td>
              <td style={styles.td} title={d.user_id}>
                {d.user_id.slice(0, 8)}…
              </td>
              <td style={{ ...styles.td, maxWidth: 320, whiteSpace: 'pre-wrap' }}>
                {d.reason}
              </td>
              <td style={styles.td}>
                <input
                  style={{ ...styles.input, width: 200 }}
                  placeholder="resolution note"
                  value={notes[d.id] ?? ''}
                  onChange={(e) => setNotes((n) => ({ ...n, [d.id]: e.target.value }))}
                />
              </td>
              <td style={styles.td}>
                <button
                  style={styles.button}
                  disabled={resolve.isPending}
                  onClick={() => act(d.id, 'resolved')}
                >
                  Resolve
                </button>{' '}
                <button
                  style={styles.button}
                  disabled={resolve.isPending}
                  onClick={() => act(d.id, 'rejected')}
                >
                  Reject
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
