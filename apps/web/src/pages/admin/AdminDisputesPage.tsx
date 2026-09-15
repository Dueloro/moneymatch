import { useState } from 'react';

import {
  useAdminDisputes,
  useResolveBucketDispute,
  useResolveDispute,
} from '../../hooks/useAdmin';
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
      <ClawbackPanel />
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

/**
 * Fault-based clawback for a bucketing dispute: void the tainted contest and
 * refund the honest players from the cheater's balance (the platform only
 * backstops a shortfall). Manual by dispute id + fault user id(s) since bucketing
 * disputes have no list endpoint yet; only works while `bucketing_enabled` is on.
 */
function ClawbackPanel() {
  const resolve = useResolveBucketDispute();
  const [disputeId, setDisputeId] = useState('');
  const [faultIds, setFaultIds] = useState('');
  const [note, setNote] = useState('');
  const [msg, setMsg] = useState<string | null>(null);

  const submit = (resolution: 'no_change' | 'refund' | 'clawback') => {
    setMsg(null);
    resolve.mutate(
      {
        dispute_id: disputeId.trim(),
        resolution,
        note: note || undefined,
        fault_player_ids: faultIds
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      },
      {
        onSuccess: () => setMsg(`Applied: ${resolution}`),
        onError: (e: unknown) => setMsg((e as Error).message),
      },
    );
  };

  return (
    <div style={{ ...styles.card, marginBottom: 16 }}>
      <h2 style={styles.h2}>Bucketing dispute — fault-based clawback</h2>
      <p style={styles.muted}>
        Void a tainted contest and refund the honest players from the cheater&apos;s
        balance. Needs bucketing enabled. Fault user ids are comma-separated.
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <input
          style={{ ...styles.input, width: 300 }}
          placeholder="bucketing dispute id"
          value={disputeId}
          onChange={(e) => setDisputeId(e.target.value)}
        />
        <input
          style={{ ...styles.input, width: 300 }}
          placeholder="fault user id(s), comma-separated"
          value={faultIds}
          onChange={(e) => setFaultIds(e.target.value)}
        />
        <input
          style={{ ...styles.input, width: 200 }}
          placeholder="note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button
          style={styles.button}
          disabled={resolve.isPending || !disputeId.trim() || !faultIds.trim()}
          onClick={() => submit('clawback')}
        >
          Clawback
        </button>
        <button
          style={styles.button}
          disabled={resolve.isPending || !disputeId.trim()}
          onClick={() => submit('refund')}
        >
          Refund
        </button>
      </div>
      {msg && <p style={styles.muted}>{msg}</p>}
    </div>
  );
}
