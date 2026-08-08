import { useEffect } from 'react';

import { useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { env } from '../lib/env';

// Query keys refreshed on any server-pushed lifecycle event. invalidateQueries
// does a prefix match, so the bare first segment also catches the user-scoped
// variants (['pool-status', userId], ['wallet', userId], ['waiting', game], …).
const REFRESH_KEYS = [
  ['activity'],
  ['pool-status'],
  ['queue-status'],
  ['waiting'],
  ['wallet'],
  ['notifications'],
] as const;

const RECONNECT_MS = 3000;

/**
 * Opens one Server-Sent Events connection to `/events/stream` and refreshes the
 * affected queries the instant the worker pushes an event (settlement, refund,
 * match found, room filled, …). This is the real event listener that replaces
 * poll latency: a cleared contest leaves In play / Room formed and lands in
 * Activity immediately, not on the next 10s tick. The existing `refetchInterval`s
 * stay as a safety net if the stream drops.
 *
 * Auth: `EventSource` can't set headers, so we trade the bearer token (in the
 * POST header — never a URL) for a single-use ticket and connect with that. The
 * ticket is one-time, so each (re)connect mints a fresh one; on any drop we
 * re-mint and reconnect ourselves rather than let EventSource retry a spent URL.
 */
export function useEventStream() {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const token = session?.access_token;

  useEffect(() => {
    // No token yet, or an environment without EventSource (SSR / jsdom tests):
    // skip the stream; the per-hook polls remain the fallback.
    if (!token || typeof EventSource === 'undefined') return;

    let source: EventSource | null = null;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const refresh = () => {
      for (const key of REFRESH_KEYS) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    };

    const scheduleReconnect = () => {
      if (stopped) return;
      reconnect = setTimeout(connect, RECONNECT_MS);
    };

    async function connect() {
      if (stopped) return;
      try {
        const res = await fetch(`${env.apiBaseUrl}/api/v1/events/ticket`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error('ticket request failed');
        const { ticket } = (await res.json()) as { ticket: string };
        if (stopped) return;

        source = new EventSource(
          `${env.apiBaseUrl}/api/v1/events/stream?ticket=${encodeURIComponent(ticket)}`,
        );
        source.onmessage = refresh;
        source.onerror = () => {
          source?.close();
          source = null;
          scheduleReconnect();
        };
      } catch {
        scheduleReconnect();
      }
    }

    connect();

    return () => {
      stopped = true;
      clearTimeout(reconnect);
      source?.close();
    };
  }, [token, queryClient]);
}
