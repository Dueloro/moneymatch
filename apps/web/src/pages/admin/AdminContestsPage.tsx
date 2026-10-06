import { useState } from 'react';

import { formatCurrency } from '../../lib/format';
import {
  useAdminContests,
  useContestDetail,
  useResettleMatch,
  useTournamentLog,
  useVoidMatch,
  useVoidTournament,
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
          placeholder="game (e.g. cs2.steam)"
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
  const voidTournament = useVoidTournament();
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

      {type === 'tournament' && ['OPEN', 'LOCKED'].includes(d.state) && (
        <div style={{ display: 'flex', gap: 8, margin: '8px 0' }}>
          <input
            style={styles.input}
            placeholder="void reason (required)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <button
            style={styles.button}
            disabled={!reason || voidTournament.isPending}
            onClick={() =>
              voidTournament.mutate(
                { tournamentId: id, reason },
                { onSuccess: () => setReason('') },
              )
            }
          >
            Void tournament → refund everyone
          </button>
        </div>
      )}

      {type === 'tournament' && <TournamentLog id={id} />}

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

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : '—';
}

/** The permanent settlement log: each entrant's result, then every match of
 * theirs we had stored, with the verdict and the host/fetch timestamps. */
function TournamentLog({ id }: { id: string }) {
  const log = useTournamentLog(id);
  if (log.isLoading) return <div style={{ marginTop: 12 }}>Loading log…</div>;
  if (log.isError || !log.data) {
    return <div style={{ ...styles.alert, marginTop: 12 }}>Couldn't load the log.</div>;
  }
  const { entrants, recorded_at, tournament_outcome } = log.data;
  return (
    <div data-testid="tournament-log">
      <h1 style={{ ...styles.h1, marginTop: 12 }}>
        Settlement log{' '}
        <span style={{ fontWeight: 400 }}>
          {recorded_at
            ? `recorded ${when(recorded_at)}${tournament_outcome ? ` · ${tournament_outcome}` : ''}`
            : '— written when the tournament finishes'}
        </span>
      </h1>
      {entrants.map((e) => (
        <div key={e.entry_id} style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, margin: '6px 0' }}>
            {e.rank ? `#${e.rank}` : '–'} {e.username ?? e.user_id.slice(0, 8)} ·{' '}
            {e.outcome} · score {e.score ?? '—'} ({e.matches_counted} counted) · paid{' '}
            {formatCurrency(e.payout_cents)} · joined {when(e.entered_at)} ·{' '}
            {e.host_account_id}
          </div>
          {e.matches.length === 0 ? (
            <div style={{ color: '#666' }}>No matches stored.</div>
          ) : (
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Match</th>
                  <th style={styles.th}>Started</th>
                  <th style={styles.th}>Ended</th>
                  <th style={styles.th}>Fetched</th>
                  <th style={styles.th}>Mode</th>
                  <th style={styles.th}>Verdict</th>
                  <th style={styles.th}>Value</th>
                  <th style={styles.th}>Stats</th>
                </tr>
              </thead>
              <tbody>
                {e.matches.map((m) => (
                  <tr key={m.host_match_id}>
                    <td style={styles.td}>{m.host_match_id}</td>
                    <td style={styles.td}>{when(m.started_at)}</td>
                    <td style={styles.td}>{when(m.ended_at)}</td>
                    <td style={styles.td}>{when(m.fetched_at)}</td>
                    <td style={styles.td}>
                      {m.mode ?? '—'}
                      {m.result ? ` · ${m.result}` : ''}
                    </td>
                    <td style={m.counted ? { ...styles.td, ...styles.ok } : styles.td}>
                      {m.reason_text}
                    </td>
                    <td style={styles.td}>{m.value ?? '—'}</td>
                    <td style={styles.td}>
                      {Object.entries(m.metrics)
                        .map(([k, v]) => `${k}=${v}`)
                        .join(' ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </div>
  );
}
