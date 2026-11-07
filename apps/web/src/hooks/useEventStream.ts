import { useEffect } from 'react';

import { useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/useAuth';
import { env } from '../lib/env';

const REFRESH_KEYS = [
  ['activity'],
  ['pool-status'],
  ['queue-status'],
  ['waiting'],
  ['wallet'],
  ['notifications'],
] as const;

const RECONNECT_MS = 3000;

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
