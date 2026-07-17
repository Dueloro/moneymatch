import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchLobby, settleContracts } from '../utils/apiClient';
import { loadState, saveState } from '../utils/storage';
import { track } from '../utils/telemetry';
import type { Contract, SettleResult } from '../types';

const STORAGE_KEY = 'contests';
const POLL_INTERVAL_MS = 15_000;

interface UseContractsArgs {
  username: string | null;
  onSettle: (contract: Contract, result: SettleResult) => void;
}

interface UseContracts {
  contracts: Contract[];
  active: Contract[];
  settled: Contract[];
  lobby: Contract[];
  lobbyLoading: boolean;
  lobbyError: string | null;
  refreshLobby: () => void;
  /** Confirm a match and escrow the entry: OPEN contest -> ACTIVE contract. */
  join: (open: Contract) => Contract;
  resetAll: () => void;
}

/**
 * Owns the user's contests (localStorage) plus the OPEN lobby and the
 * settlement poll loop. Settlement is server-authoritative: we POST the user's
 * in-flight contests and the server grades them against the user's real games.
 * The poll cadence + abort handling are shaped so a server-side worker can
 * replace the client loop without a UI rewrite (roadmap §1.5).
 */
export function useContracts({ username, onSettle }: UseContractsArgs): UseContracts {
  const [contracts, setContracts] = useState<Contract[]>(() =>
    loadState<Contract[]>(STORAGE_KEY, []),
  );
  const [lobby, setLobby] = useState<Contract[]>([]);
  const [lobbyLoading, setLobbyLoading] = useState(false);
  const [lobbyError, setLobbyError] = useState<string | null>(null);

  useEffect(() => {
    saveState(STORAGE_KEY, contracts);
  }, [contracts]);

  const active = useMemo(
    () => contracts.filter((c) => c.state === 'ACTIVE' || c.state === 'RESOLVING'),
    [contracts],
  );
  const settled = useMemo(
    () => contracts.filter((c) => c.state === 'SETTLED' || c.state === 'CANCELED'),
    [contracts],
  );

  // ---- Lobby ----
  const refreshLobby = useCallback(() => {
    if (!username) return;
    setLobbyLoading(true);
    setLobbyError(null);
    fetchLobby(username)
      .then((res) => {
        setLobby(res.contests);
        track('lobby_refreshed', { username, count: res.contests.length });
      })
      .catch((err: Error) => setLobbyError(err.message || 'Failed to load the lobby'))
      .finally(() => setLobbyLoading(false));
  }, [username]);

  useEffect(() => {
    if (username) refreshLobby();
    else setLobby([]);
  }, [username, refreshLobby]);

  // ---- Join (confirm match + escrow entry) ----
  const join = useCallback((open: Contract): Contract => {
    const contract: Contract = {
      ...open,
      state: 'ACTIVE',
      matched_at: Date.now(),
      resolved_at: null,
      qualifying_game_ids: [],
      progress: null,
      winner: null,
      outcome: null,
    };
    setContracts((prev) => [contract, ...prev]);
    track('match_confirmed', {
      kind: open.objective.kind,
      speed: open.speed,
      entry: open.entry,
      opponent_rating: open.opponent.rating,
    });
    return contract;
  }, []);

  const resetAll = useCallback(() => setContracts([]), []);

  // ---- Settlement poll loop ----
  const ref = useRef({ contracts, username, onSettle });
  ref.current = { contracts, username, onSettle };
  const inFlight = useRef(false);

  const settleOnce = useCallback(async (signal?: AbortSignal) => {
    const { contracts: all, username: user, onSettle: notify } = ref.current;
    if (!user || inFlight.current) return;
    const live = all.filter((c) => c.state === 'ACTIVE' || c.state === 'RESOLVING');
    if (live.length === 0) return;

    inFlight.current = true;
    try {
      const { results } = await settleContracts(user, live, signal);
      if (signal?.aborted) return;
      const byId = new Map(results.map((r) => [r.id, r]));

      // Compute transitions from the current snapshot, fire callbacks once.
      const transitions: { contract: Contract; result: SettleResult }[] = [];

      setContracts((prev) =>
        prev.map((c) => {
          const r = byId.get(c.id);
          if (!r || (c.state !== 'ACTIVE' && c.state !== 'RESOLVING')) return c;
          if (r.state === 'SETTLED' || r.state === 'CANCELED') {
            const updated: Contract = {
              ...c,
              state: r.state,
              outcome: r.outcome,
              winner: r.winner,
              resolved_at: r.resolved_at,
              qualifying_game_ids: r.qualifying_game_ids,
              progress: r.progress,
            };
            transitions.push({ contract: updated, result: r });
            return updated;
          }
          return {
            ...c,
            qualifying_game_ids: r.qualifying_game_ids,
            progress: r.progress,
          };
        }),
      );

      for (const t of transitions) {
        track('contest_settled', { outcome: t.result.outcome, winner: t.result.winner, payout: t.result.payout });
        if (t.result.outcome === 'won') {
          track('rake_collected', { rake: t.contract.rake });
        }
        notify(t.contract, t.result);
      }
    } catch {
      // Leave contests live; retry on the next poll.
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void settleOnce(controller.signal);
    const id = window.setInterval(() => void settleOnce(controller.signal), POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      window.clearInterval(id);
    };
  }, [settleOnce]);

  return {
    contracts,
    active,
    settled,
    lobby,
    lobbyLoading,
    lobbyError,
    refreshLobby,
    join,
    resetAll,
  };
}
