import { useEffect, useRef, useState } from 'react';
import { fetchSpectate } from '../utils/apiClient';
import type { SpectateResponse } from '../types';

const POLL_MS = 5_000;

interface UseSpectate {
  state: SpectateResponse | null;
  loading: boolean;
  error: string | null;
}

/**
 * Polls the user's current Lichess game while ``enabled`` (the spectator panel
 * is open). Sourced live from the public current-game endpoint; stops polling
 * once the game is finished or the panel is closed.
 */
export function useSpectate(username: string | null, enabled: boolean): UseSpectate {
  const [state, setState] = useState<SpectateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const finishedRef = useRef(false);

  useEffect(() => {
    if (!enabled || !username) {
      setState(null);
      setError(null);
      finishedRef.current = false;
      return;
    }

    const controller = new AbortController();
    let timer: number | undefined;

    const poll = async () => {
      setLoading(true);
      try {
        const res = await fetchSpectate(username, controller.signal);
        if (controller.signal.aborted) return;
        setState(res);
        setError(null);
        finishedRef.current = res.finished;
      } catch (err) {
        if (!controller.signal.aborted) setError((err as Error).message || 'Failed to load the game');
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          // Keep refreshing only while the game is live.
          if (!finishedRef.current) timer = window.setTimeout(poll, POLL_MS);
        }
      }
    };
    void poll();

    return () => {
      controller.abort();
      if (timer) window.clearTimeout(timer);
    };
  }, [username, enabled]);

  return { state, loading, error };
}
