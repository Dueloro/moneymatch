import { useState } from 'react';

import { useAdminGameMatches, type AdminGameMatch } from '../../hooks/useAdmin';
import { styles } from './adminStyles';

const GAMES = ['', 'chess.lichess', 'pubg.steam', 'cs2.steam', 'dota2.opendota'];

function time(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : '—';
}

function statsOf(m: AdminGameMatch): string {
  const parts = Object.entries(m.metrics).map(([k, v]) => `${k}=${v}`);
  if (m.game === 'chess.lichess') {
    const d = m.detail as {
      opponent_id?: string;
      opponent_rating?: number;
      opponent_provisional?: boolean;
    };
    parts.push(`moves=${m.moves}`);
    if (d.opponent_id) {
      parts.push(
        `vs ${d.opponent_id} (${d.opponent_rating ?? '?'}${d.opponent_provisional ? ', provisional' : ''})`,
      );
    }
  } else if (m.game === 'pubg.steam') {
    const d = m.detail as { win_place?: number; match_type?: string };
    if (d.win_place != null) parts.push(`place=#${d.win_place}`);
    if (d.match_type) parts.push(d.match_type);
  }
  return parts.join(' · ');
}

/**
 * Every game the background ingester has fetched and stored — what tournaments
 * are scored from. Filter by username / host handle and game.
 */
export function AdminMatchesPage() {
  const [player, setPlayer] = useState('');
  const [game, setGame] = useState('');
  const [applied, setApplied] = useState<{ player?: string; game?: string }>({});
  const matches = useAdminGameMatches(applied);

  return (
    <div style={styles.page}>
      <h1 style={styles.h1}>Stored matches (background ingestion, newest first)</h1>
      <form
        style={{ display: 'flex', gap: 8, marginBottom: 12 }}
        onSubmit={(e) => {
          e.preventDefault();
          setApplied({ player: player.trim(), game });
        }}
      >
        <input
          style={styles.input}
          placeholder="username or host handle"
          value={player}
          onChange={(e) => setPlayer(e.target.value)}
        />
        <select
          style={styles.input}
          value={game}
          onChange={(e) => setGame(e.target.value)}
        >
          {GAMES.map((g) => (
            <option key={g} value={g}>
              {g || 'all games'}
            </option>
          ))}
        </select>
        <button style={styles.button} type="submit">
          Filter
        </button>
      </form>

      {matches.isLoading ? (
        <div>Loading…</div>
      ) : matches.isError ? (
        <div style={styles.alert}>{(matches.error as Error).message}</div>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Player</th>
              <th style={styles.th}>Game</th>
              <th style={styles.th}>Started</th>
              <th style={styles.th}>Ended</th>
              <th style={styles.th}>Mode</th>
              <th style={styles.th}>Counts?</th>
              <th style={styles.th}>Result</th>
              <th style={styles.th}>Stats</th>
              <th style={styles.th}>Match id</th>
              <th style={styles.th}>Fetched</th>
              <th style={styles.th}>Account last polled</th>
            </tr>
          </thead>
          <tbody>
            {(matches.data ?? []).map((m) => (
              <tr key={m.id}>
                <td style={styles.td}>
                  {m.username ?? '?'}
                  <br />
                  <span style={{ color: '#666' }}>{m.host_username}</span>
                </td>
                <td style={styles.td}>{m.game}</td>
                <td style={styles.td}>{time(m.started_at)}</td>
                <td style={styles.td}>{time(m.ended_at)}</td>
                <td style={styles.td}>{m.mode ?? '—'}</td>
                <td style={styles.td}>
                  {m.eligible ? (m.rated ? 'yes' : 'unrated') : 'no (mode)'}
                </td>
                <td style={styles.td}>{m.result ?? '—'}</td>
                <td style={styles.td}>{statsOf(m)}</td>
                <td style={styles.td}>{m.host_match_id}</td>
                <td style={styles.td}>{time(m.fetched_at)}</td>
                <td style={styles.td}>{time(m.account_last_polled_at)}</td>
              </tr>
            ))}
            {(matches.data ?? []).length === 0 && (
              <tr>
                <td style={styles.td} colSpan={11}>
                  No stored matches yet. Accounts are polled in the background (every 2
                  min while in a contest, every 6 h otherwise).
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
