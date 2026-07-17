import { useState } from 'react';

import { formatCurrency } from '../../lib/format';
import {
  useAdminContests,
  useContestDetail,
  useResettleMatch,
  useVoidMatch,
} from '../../hooks/useAdmin';
import { styles } from './adminStyles';

export function AdminContestsPage() {
  const [state, setState] = useState('');
  const [game, setGame] = useState('');
  const [selected, setSelected] = useState<{ type: string; id: string } | null>(null);
  const contests = useAdminContests({
    state: state || undefined,
    game: game || undefined,
  });

  return (
    <div style={styles.page}>
      <h1 style={styles.h1}>Contests</h1>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <input
          style={styles.input}
          placeholder="state (e.g. ACTIVE)"
          value={state}
          onChange={(e) => setState(e.target.value)}
        />
        <input
          style={styles.input}
          placeholder="game (e.g. cs2.faceit)"
          value={game}
          onChange={(e) => setGame(e.target.value)}
        />
      </div>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Type</th>
            <th style={styles.th}>Game</th>
            <th style={styles.th}>Market</th>
            <th style={styles.th}>State</th>
            <th style={styles.th}>Pot</th>
            <th style={styles.th}>Players</th>
            <th style={styles.th}></th>
          </tr>
        </thead>
        <tbody>
          {(contests.data ?? []).map((c) => (
            <tr key={c.ref_id}>
              <td style={styles.td}>{c.ref_type}</td>
              <td style={styles.td}>{c.game}</td>
              <td style={styles.td}>{c.market}</td>
              <td style={styles.td}>{c.state}</td>
              <td style={styles.td}>{formatCurrency(c.pot_cents)}</td>
              <td style={styles.td}>{c.participants}</td>
              <td style={styles.td}>
                <button
                  style={styles.button}
                  onClick={() => setSelected({ type: c.ref_type, id: c.ref_id })}
                >
                  Open
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {selected && <ContestDetail type={selected.type} id={selected.id} />}
    </div>
  );
}

function ContestDetail({ type, id }: { type: string; id: string }) {
  const detail = useContestDetail(type, id);
  const resettle = useResettleMatch();
  const voidMatch = useVoidMatch();
  const [reason, setReason] = useState('');

  if (detail.isLoading) return <div style={{ marginTop: 16 }}>Loading…</div>;
  const d = detail.data as
    | {
        state: string;
        reconciliation: { ok: boolean };
        ledger: {
          id: string;
          username: string | null;
          entry_type: string;
          amount_cents: number;
        }[];
        platform_ledger: { account: string; amount_cents: number }[];
        outcome_detail: unknown;
      }
    | undefined;
  if (!d) return null;

  return (
    <div style={{ marginTop: 20, borderTop: '2px solid #333', paddingTop: 12 }}>
      <h1 style={styles.h1}>
        {type} {id.slice(0, 8)} — {d.state}{' '}
        <span style={d.reconciliation.ok ? styles.ok : styles.alert}>
          recon {d.reconciliation.ok ? 'OK' : 'BREACH'}
        </span>
      </h1>
      {type === 'match' && (
        <div style={{ display: 'flex', gap: 8, margin: '8px 0' }}>
          <button style={styles.button} onClick={() => resettle.mutate(id)}>
            Re-settle
          </button>
          <input
            style={styles.input}
            placeholder="void reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <button
            style={styles.button}
            disabled={!reason}
            onClick={() =>
              voidMatch.mutate(
                { matchId: id, reason },
                { onSuccess: () => setReason('') },
              )
            }
          >
            Void → refund
          </button>
        </div>
      )}

      <h1 style={{ ...styles.h1, marginTop: 12 }}>Ledger (money trail)</h1>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>User</th>
            <th style={styles.th}>Type</th>
            <th style={styles.th}>Amount</th>
          </tr>
        </thead>
        <tbody>
          {d.ledger.map((r) => (
            <tr key={r.id}>
              <td style={styles.td}>{r.username ?? '—'}</td>
              <td style={styles.td}>{r.entry_type}</td>
              <td style={styles.td}>{formatCurrency(r.amount_cents)}</td>
            </tr>
          ))}
          {d.platform_ledger.map((p, i) => (
            <tr key={`p${i}`}>
              <td style={styles.td}>{p.account}</td>
              <td style={styles.td}>platform</td>
              <td style={styles.td}>{formatCurrency(p.amount_cents)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h1 style={{ ...styles.h1, marginTop: 12 }}>Adapter evidence</h1>
      <pre style={styles.pre}>{JSON.stringify(d.outcome_detail, null, 2)}</pre>
    </div>
  );
}
