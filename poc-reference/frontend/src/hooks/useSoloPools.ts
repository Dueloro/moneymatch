import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  enterSoloPool,
  fetchFaceitTelemetry,
  fetchSoloLobby,
  settleSoloPool,
} from '../utils/apiClient';
import { genTelemetry } from '../utils/soloText';
import { loadState, saveState } from '../utils/storage';
import { track } from '../utils/telemetry';
import type { SoloPool, TelemetrySample } from '../types';

const STORAGE_KEY = 'solo_pools';
// Demo only: roughly how often a bot entrant clears the standard.
const BOT_CLEAR_RATE = 0.55;

interface UseSoloPoolsArgs {
  username: string | null;
  residenceState: string | null;
}

interface UseSoloPools {
  lobby: SoloPool[]; // open pools the player hasn't joined
  mine: SoloPool[]; // pools the player has entered (LOCKED / SETTLED / CANCELED)
  loading: boolean;
  error: string | null;
  refresh: () => void;
  /** Escrow into a pool (geo-checked server-side). Throws on 403 / API error. */
  join: (pool: SoloPool) => Promise<SoloPool>;
  /** Simulate match telemetry for all entrants and settle the pool. */
  settle: (poolId: string, userCleared: boolean) => Promise<SoloPool>;
  reset: () => void;
}

/**
 * Owns the pooled solo-tournament lobby plus the player's entered pools
 * (localStorage). Joining and settling go through the backend solo engine, so
 * the escrow/rake invariant is enforced server-side. Telemetry is mocked in the
 * demo (genTelemetry) — in production it arrives from the game's data webhook.
 */
export function useSoloPools({ username, residenceState }: UseSoloPoolsArgs): UseSoloPools {
  const [lobbyPools, setLobbyPools] = useState<SoloPool[]>([]);
  const [mine, setMine] = useState<SoloPool[]>(() => loadState<SoloPool[]>(STORAGE_KEY, []));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    saveState(STORAGE_KEY, mine);
  }, [mine]);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchSoloLobby()
      .then((res) => setLobbyPools(res.pools))
      .catch((err: Error) => setError(err.message || 'Failed to load solo pools'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Open pools the player hasn't already joined.
  const mineIds = useMemo(() => new Set(mine.map((p) => p.id)), [mine]);
  const lobby = useMemo(() => lobbyPools.filter((p) => !mineIds.has(p.id)), [lobbyPools, mineIds]);

  const join = useCallback(
    async (pool: SoloPool): Promise<SoloPool> => {
      if (!username) throw new Error('Link a Lichess account first.');
      if (!residenceState) throw new Error('Set your region first.');
      const entered = await enterSoloPool(pool, username, residenceState);
      setMine((prev) => [entered, ...prev.filter((p) => p.id !== entered.id)]);
      track('entry_queued', { feature: 'solo', game: pool.game, entry: pool.entry_fee });
      return entered;
    },
    [username, residenceState],
  );

  const settle = useCallback(
    async (poolId: string, userCleared: boolean): Promise<SoloPool> => {
      const pool = mine.find((p) => p.id === poolId);
      if (!pool) throw new Error('Pool not found.');

      // For CS2 the player's entry grades against their REAL latest FaceIt match
      // (server reads it via the dev telemetry route), not a mocked clear/miss.
      // Falls back to the button if the live fetch fails. Bots stay mocked.
      let userTelemetry: TelemetrySample | null = null;
      if (pool.game === 'cs2.faceit' && username) {
        try {
          const t = await fetchFaceitTelemetry(username);
          userTelemetry = { game: pool.game, metrics: t.metrics };
        } catch {
          userTelemetry = null;
        }
      }

      // Telemetry for every entrant: the player uses real CS2 stats when
      // available else the clear/miss button; bots clear at BOT_CLEAR_RATE.
      const telemetry: Record<string, TelemetrySample> = {};
      for (const e of pool.entrants) {
        if (e.player_id === username && userTelemetry) {
          telemetry[e.player_id] = userTelemetry;
          continue;
        }
        const cleared = e.player_id === username ? userCleared : Math.random() < BOT_CLEAR_RATE;
        telemetry[e.player_id] = genTelemetry(pool.metric_target, pool.game, cleared);
      }

      const settled = await settleSoloPool(pool, telemetry);
      setMine((prev) => prev.map((p) => (p.id === settled.id ? settled : p)));
      track('contest_settled', {
        feature: 'solo',
        status: settled.status,
        rake: settled.rake,
        clearers: settled.entrants.filter((e) => e.status === 'CLEARED').length,
      });
      if (settled.rake > 0) track('rake_collected', { feature: 'solo', rake: settled.rake });
      return settled;
    },
    [mine, username],
  );

  const reset = useCallback(() => setMine([]), []);

  return { lobby, mine, loading, error, refresh, join, settle, reset };
}
