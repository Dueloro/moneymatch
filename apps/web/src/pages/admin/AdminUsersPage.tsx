import { useState } from 'react';

import { formatCurrency } from '../../lib/format';
import {
  useAdjustUser,
  useAdminUser,
  useAdminUsers,
  useFreezeUser,
} from '../../hooks/useAdmin';
import { styles } from './adminStyles';

export function AdminUsersPage() {
  const [q, setQ] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const users = useAdminUsers(q);

  return (
    <div style={styles.page}>
      <h1 style={styles.h1}>Users</h1>
      <input
        style={{ ...styles.input, width: 320 }}
        placeholder="search username / email / friend code / id"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <table style={{ ...styles.table, marginTop: 12 }}>
        <thead>
          <tr>
            <th style={styles.th}>Username</th>
            <th style={styles.th}>Email</th>
            <th style={styles.th}>Role</th>
            <th style={styles.th}>Status</th>
            <th style={styles.th}>Available</th>
            <th style={styles.th}>Escrow</th>
            <th style={styles.th}></th>
          </tr>
        </thead>
        <tbody>
          {(users.data ?? []).map((u) => (
            <tr key={u.id}>
              <td style={styles.td}>{u.username ?? '—'}</td>
              <td style={styles.td}>{u.email ?? '—'}</td>
              <td style={styles.td}>{u.role}</td>
              <td style={styles.td}>
                <span style={u.status === 'active' ? styles.ok : styles.alert}>
                  {u.status}
                </span>
              </td>
              <td style={styles.td}>{formatCurrency(u.available_cents)}</td>
              <td style={styles.td}>{formatCurrency(u.escrow_cents)}</td>
              <td style={styles.td}>
                <button style={styles.button} onClick={() => setSelected(u.id)}>
                  Open
                </button>
              </td>
            </tr>
          ))}
          {users.data?.length === 0 && (
            <tr>
              <td style={styles.td} colSpan={7}>
                No users.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {selected && <UserDetail userId={selected} />}
    </div>
  );
}

function UserDetail({ userId }: { userId: string }) {
  const detail = useAdminUser(userId);
  const freeze = useFreezeUser(userId);
  const adjust = useAdjustUser(userId);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');

  if (detail.isLoading) return <div style={{ marginTop: 16 }}>Loading detail…</div>;
  const d = detail.data as
    | {
        username: string | null;
        status: string;
        available_cents: number;
        escrow_cents: number;
        lifetime_net_cents: number;
        linked_accounts: { id: string; game: string; host_username: string }[];
        contests: {
          ref_type: string;
          ref_id: string;
          market: string;
          state: string;
          payout_cents: number;
        }[];
        recent_ledger: {
          id: string;
          entry_type: string;
          amount_cents: number;
          memo: string | null;
        }[];
      }
    | undefined;
  if (!d) return null;

  return (
    <div style={{ marginTop: 20, borderTop: '2px solid #333', paddingTop: 12 }}>
      <h1 style={styles.h1}>
        {d.username ?? userId} — {d.status}
      </h1>
      <p>
        available {formatCurrency(d.available_cents)} · escrow{' '}
        {formatCurrency(d.escrow_cents)} · lifetime{' '}
        {formatCurrency(d.lifetime_net_cents)}
      </p>
      <div style={{ display: 'flex', gap: 8, margin: '8px 0' }}>
        <button
          style={styles.button}
          onClick={() => freeze.mutate(d.status === 'active')}
        >
          {d.status === 'active' ? 'Freeze' : 'Unfreeze'}
        </button>
        <input
          style={{ ...styles.input, width: 120 }}
          placeholder="cents (+/-)"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <input
          style={{ ...styles.input, width: 220 }}
          placeholder="reason (required)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <button
          style={styles.button}
          disabled={!reason || !amount}
          onClick={() =>
            adjust.mutate(
              { amount_cents: parseInt(amount, 10), reason },
              {
                onSuccess: () => {
                  setAmount('');
                  setReason('');
                },
              },
            )
          }
        >
          Adjust ledger
        </button>
      </div>

      <h1 style={{ ...styles.h1, marginTop: 12 }}>Linked accounts</h1>
      <ul>
        {d.linked_accounts.map((l) => (
          <li key={l.id}>
            {l.game}: {l.host_username}
          </li>
        ))}
        {d.linked_accounts.length === 0 && <li>none</li>}
      </ul>

      <h1 style={{ ...styles.h1, marginTop: 12 }}>Contests</h1>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Type</th>
            <th style={styles.th}>Market</th>
            <th style={styles.th}>State</th>
            <th style={styles.th}>Payout</th>
          </tr>
        </thead>
        <tbody>
          {d.contests.map((c) => (
            <tr key={c.ref_id}>
              <td style={styles.td}>{c.ref_type}</td>
              <td style={styles.td}>{c.market}</td>
              <td style={styles.td}>{c.state}</td>
              <td style={styles.td}>{formatCurrency(c.payout_cents)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h1 style={{ ...styles.h1, marginTop: 12 }}>Recent ledger</h1>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Type</th>
            <th style={styles.th}>Amount</th>
            <th style={styles.th}>Memo</th>
          </tr>
        </thead>
        <tbody>
          {d.recent_ledger.map((r) => (
            <tr key={r.id}>
              <td style={styles.td}>{r.entry_type}</td>
              <td style={styles.td}>{formatCurrency(r.amount_cents)}</td>
              <td style={styles.td}>{r.memo ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
