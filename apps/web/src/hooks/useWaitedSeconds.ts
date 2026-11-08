import { useEffect, useRef, useState } from 'react';

/**
 * A once-a-second clock seeded by the server's `waited_seconds` (polled every
 * 2s). A new server value re-seeds it only if it is more than 2s off, so the
 * clock never stutters backwards between polls.
 */
export function useWaitedSeconds(server: number | null | undefined): number {
  const anchor = useRef({ base: server ?? 0, at: Date.now(), server });
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const a = anchor.current;
  const local = a.base + (now - a.at) / 1000;
  if (server != null && server !== a.server) {
    a.server = server;
    if (Math.abs(local - server) > 2) {
      anchor.current = { base: server, at: now, server };
      return server;
    }
  }
  return Math.max(0, Math.floor(local));
}
