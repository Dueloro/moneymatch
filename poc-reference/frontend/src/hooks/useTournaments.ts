import { useCallback, useEffect, useMemo, useState } from 'react';
import { enterTournament, fetchTournamentLobby, settleTournament } from '../utils/apiClient';
import { genScore } from '../utils/tournamentText';
import { loadState, saveState } from '../utils/storage';
import { track } from '../utils/telemetry';
import type { TelemetrySample, Tournament } from '../types';

const STORAGE_KEY = 'tournaments';

interface UseTournamentsArgs {
  username: string | null;
  residenceState: string | null;
}

interface UseTournaments {
  lobby: Tournament[]; // open tournaments the player hasn't joined
  mine: Tournament[]; // tournaments the player has entered
  loading: boolean;
  error: string | null;
  refresh: () => void;
  /** Escrow into a tournament (geo-checked server-side). Throws on 403/409/error. */
  join: (t: Tournament) => Promise<Tournament>;
  /** Simulate every entrant's run and settle: rank, pay top-N minus rake. */
  settle: (tournamentId: string) => Promise<Tournament>;
  reset: () => void;
}

/**
 * Owns the tournament lobby plus the player's entered tournaments
 * (localStorage). Joining and settling go through the backend tournament
 * engine, so the escrow/rake invariant is enforced server-side. Telemetry is
 * mocked in the demo (genScore); in production it arrives from the game webhook.
 */
export function useTournaments({ username, residenceState }: UseTournamentsArgs): UseTournaments {
  const [lobbyTs, setLobbyTs] = useState<Tournament[]>([]);
  const [mine, setMine] = useState<Tournament[]>(() => loadState<Tournament[]>(STORAGE_KEY, []));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    saveState(STORAGE_KEY, mine);
  }, [mine]);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchTournamentLobby()
      .then((res) => setLobbyTs(res.tournaments))
      .catch((err: Error) => setError(err.message || 'Failed to load tournaments'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const mineIds = useMemo(() => new Set(mine.map((t) => t.id)), [mine]);
  const lobby = useMemo(() => lobbyTs.filter((t) => !mineIds.has(t.id)), [lobbyTs, mineIds]);

  const join = useCallback(
    async (t: Tournament): Promise<Tournament> => {
      if (!username) throw new Error('Link a Lichess account first.');
      if (!residenceState) throw new Error('Set your region first.');
      const entered = await enterTournament(t, username, residenceState);
      setMine((prev) => [entered, ...prev.filter((p) => p.id !== entered.id)]);
      track('entry_queued', { feature: 'tournament', game: t.game, entry: t.entry_fee });
      return entered;
    },
    [username, residenceState],
  );

  const settle = useCallback(
    async (tournamentId: string): Promise<Tournament> => {
      const t = mine.find((p) => p.id === tournamentId);
      if (!t) throw new Error('Tournament not found.');

      // Mock a run for every entrant: the human player gets a "strong" bias so
      // the demo isn't hopeless; bots get the full range.
      const telemetry: Record<string, TelemetrySample> = {};
      for (const e of t.entrants) {
        telemetry[e.player_id] = genScore(t.ranking_metric, t.game, e.player_id === username);
      }

      const settled = await settleTournament(t, telemetry);
      setMine((prev) => prev.map((p) => (p.id === settled.id ? settled : p)));
      track('contest_settled', {
        feature: 'tournament',
        status: settled.status,
        rake: settled.rake,
        paid: settled.entrants.filter((e) => e.status === 'PAID').length,
      });
      if (settled.rake > 0) track('rake_collected', { feature: 'tournament', rake: settled.rake });
      return settled;
    },
    [mine, username],
  );

  const reset = useCallback(() => setMine([]), []);

  return { lobby, mine, loading, error, refresh, join, settle, reset };
}
