import { useCallback, useEffect, useRef, useState } from 'react';
import { mmCancel, mmConfirm, mmMatch, mmPoll, mmQueue, mmSettle } from '../utils/apiClient';
import type { Match, MatchPlayer } from '../types';

export type MmPhase = 'idle' | 'searching' | 'pending' | 'active' | 'done';

export interface MmPlayer {
  id: string;
  name: string;
  rating: number;
}

interface UseMatchmakingArgs {
  game: string;
  me: MmPlayer | null;
  /** Escrow the entry when both players confirm (available → escrow). */
  onEscrow: (entry: number) => void;
  /** Fire once when a match we escrowed into resolves (settle or refund). */
  onResolved: (match: Match, mine: MatchPlayer | undefined) => void;
}

interface UseMatchmaking {
  phase: MmPhase;
  match: Match | null;
  mine: MatchPlayer | undefined;
  opponent: MatchPlayer | undefined;
  escrowed: boolean;
  error: string | null;
  find: (entry: number, speed: string, format: string) => Promise<void>;
  confirm: () => Promise<void>;
  cancel: () => Promise<void>;
  reset: () => void;
}

const SEARCH_POLL_MS = 2000;
const SETTLE_POLL_MS = 5000;

/**
 * Client state machine for real head-to-head matchmaking: queue → pair → confirm
 * → play → settle. Escrows on both-confirm (ACTIVE) and reconciles the wallet
 * once the shared match resolves. Polls the server for the pieces that happen in
 * the other player's session.
 */
export function useMatchmaking({ game, me, onEscrow, onResolved }: UseMatchmakingArgs): UseMatchmaking {
  const [phase, setPhase] = useState<MmPhase>('idle');
  const [match, setMatch] = useState<Match | null>(null);
  const [error, setError] = useState<string | null>(null);
  const escrowedRef = useRef<string | null>(null);
  const resolvedRef = useRef<string | null>(null);

  const mine = me && match ? match.players.find((p) => p.player_id === me.id) : undefined;
  const opponent = me && match ? match.players.find((p) => p.player_id !== me.id) : undefined;
  const escrowed = !!match && escrowedRef.current === match.id;

  const find = useCallback(async (entry: number, speed: string, format: string) => {
    if (!me) return;
    setError(null);
    try {
      const res = await mmQueue({ player_id: me.id, display_name: me.name, game, speed, format, entry, rating: me.rating });
      if (res.status === 'matched' && res.match) { setMatch(res.match); setPhase('pending'); }
      else setPhase('searching');
    } catch (e) {
      setError((e as Error).message || 'Could not join the queue');
    }
  }, [me, game]);

  const confirm = useCallback(async () => {
    if (!me || !match) return;
    try { setMatch(await mmConfirm(match.id, me.id)); }
    catch (e) { setError((e as Error).message); }
  }, [me, match]);

  const reset = useCallback(() => { setMatch(null); setPhase('idle'); setError(null); }, []);

  const cancel = useCallback(async () => {
    if (me) { try { await mmCancel(match?.id ?? '', me.id); } catch { /* ignore */ } }
    reset();
  }, [me, match, reset]);

  // Poll the piece that lives in the other player's session, per phase.
  useEffect(() => {
    if (!me) return;
    let timer: number | undefined;
    if (phase === 'searching') {
      timer = window.setInterval(async () => {
        try {
          const res = await mmPoll(me.id);
          if (res.status === 'matched' && res.match) { setMatch(res.match); setPhase('pending'); }
        } catch { /* ignore */ }
      }, SEARCH_POLL_MS);
    } else if (phase === 'pending' && match) {
      timer = window.setInterval(async () => {
        try { setMatch(await mmMatch(match.id)); } catch { /* ignore */ }
      }, SEARCH_POLL_MS);
    } else if (phase === 'active' && match) {
      timer = window.setInterval(async () => {
        try { setMatch(await mmSettle(match.id, me.id)); } catch { /* ignore */ }
      }, SETTLE_POLL_MS);
    }
    return () => { if (timer) window.clearInterval(timer); };
  }, [phase, match?.id, me]);

  // React to lifecycle transitions: escrow on ACTIVE, reconcile on resolve.
  useEffect(() => {
    if (!match || !me) return;
    if (match.state === 'ACTIVE') {
      if (escrowedRef.current !== match.id) { escrowedRef.current = match.id; onEscrow(match.entry); }
      setPhase((p) => (p === 'active' ? p : 'active'));
    } else if (match.state === 'SETTLED' || match.state === 'CANCELED') {
      // Only reconcile the wallet if we actually escrowed (i.e. it reached ACTIVE);
      // a decline during PENDING never took the entry.
      if (escrowedRef.current === match.id && resolvedRef.current !== match.id) {
        resolvedRef.current = match.id;
        onResolved(match, match.players.find((p) => p.player_id === me.id));
      }
      setPhase((p) => (p === 'done' ? p : 'done'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [match?.state, match?.id]);

  return { phase, match, mine, opponent, escrowed, error, find, confirm, cancel, reset };
}
