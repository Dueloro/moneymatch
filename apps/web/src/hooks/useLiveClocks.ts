import { useEffect, useState } from 'react';

import type { MatchLive } from './useMatchmaking';

export interface LiveClocks {
  you: number;
  opp: number;
  /** Whose clock is running, or null when neither is (not started, or over). */
  running: 'you' | 'opp' | null;
}

/** Remaining ms per side, counting the running clock down locally between refreshes. */
export function liveClocks(
  live: MatchLive | null | undefined,
  now: number,
): LiveClocks | null {
  if (!live?.clocks || !live.your_color) return null;
  const mine =
    live.your_color === 'white' ? live.clocks.white_ms : live.clocks.black_ms;
  const theirs =
    live.your_color === 'white' ? live.clocks.black_ms : live.clocks.white_ms;
  // Lichess starts the clocks once both sides have moved.
  const running =
    live.status === 'live' && (live.san?.length ?? 0) >= 2 ? (live.turn ?? null) : null;
  const since = live.last_move_at ? Date.parse(live.last_move_at) : NaN;
  const elapsed = running && Number.isFinite(since) ? Math.max(0, now - since) : 0;
  return {
    you: Math.max(0, mine - (running === 'you' ? elapsed : 0)),
    opp: Math.max(0, theirs - (running === 'opp' ? elapsed : 0)),
    running,
  };
}

export function useLiveClocks(live: MatchLive | null | undefined): LiveClocks | null {
  const [now, setNow] = useState(() => Date.now());
  const ticking = liveClocks(live, now)?.running != null;
  useEffect(() => {
    if (!ticking) return;
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [ticking]);
  return liveClocks(live, now);
}

/** "4:05", or "0:08.4" in the last ten seconds. */
export function formatClock(ms: number): string {
  if (ms < 10_000) return `0:0${(Math.floor(ms / 100) / 10).toFixed(1)}`;
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}
