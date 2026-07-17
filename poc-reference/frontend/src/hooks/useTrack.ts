import { useEffect, useRef, useState } from 'react';
import { fetchTrack } from '../utils/apiClient';
import type { MatchTrackerResponse } from '../types';

const POLL_MS = 8_000;

interface UseTrack {
  state: MatchTrackerResponse | null;
  loading: boolean;
  error: string | null;
}

/**
 * Polls the player's current / most-recent match for CS2 or Dota while the
 * tracker panel is open. Keeps refreshing while a match reads as "Live".
 */
export function useTrack(game: string, username: string | null, enabled: boolean): UseTrack {
  const [state, setState] = useState<MatchTrackerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const liveRef = useRef(false);

  useEffect(() => {
    if (!enabled || !username) {
      setState(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    let timer: number | undefined;

    const poll = async () => {
      setLoading(true);
      try {
        const res = await fetchTrack(game, username, controller.signal);
        if (controller.signal.aborted) return;
        setState(res);
        setError(null);
        liveRef.current = res.status === 'Live';
      } catch (err) {
        if (!controller.signal.aborted) setError((err as Error).message || 'Failed to load the match');
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          // Keep refreshing while the match is live; otherwise one fetch is enough.
          if (liveRef.current) timer = window.setTimeout(poll, POLL_MS);
        }
      }
    };
    void poll();

    return () => {
      controller.abort();
      if (timer) window.clearTimeout(timer);
    };
  }, [game, username, enabled]);

  return { state, loading, error };
}
