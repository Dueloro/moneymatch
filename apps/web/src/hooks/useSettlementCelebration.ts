import { useCallback, useEffect, useRef, useState } from 'react';

import type { ActivityItem } from './useActivity';
import { useActivity } from './useActivity';
import type { Termination } from './useMatchmaking';

/**
 * A new key releases them; the `RECENT_MS` window on first load keeps that
 * from turning into a replay of your whole history.
 */
const STORAGE_KEY = 'mm.announced-settlements.v2';

const TERMINAL = new Set(['SETTLED', 'PUSHED', 'CANCELED']);

const MAX_REMEMBERED = 400;

const MAX_BURST = 3;

const RECENT_MS = 60 * 60 * 1000;

export type SettlementOutcome = 'win' | 'loss' | 'push' | 'refund';

export interface Settlement {
  id: string;
  outcome: SettlementOutcome;
  netCents: number;
  amountCents: number;
  balanceDeltaCents: number;
  title: string;
  game: string;
  type: ActivityItem['type'];
  entryCents?: number;
  prizeCents?: number;
  opponent?: string | null;
  termination?: Termination | null;
}

/**
 * Only a pool or tournament win takes the screen (a light card). Head to head has
 * its result card on the match stage; everything else is a quiet toast.
 */
export function surfaceOf(s: Settlement): 'overlay' | 'toast' {
  return s.outcome === 'win' && s.type !== 'match' ? 'overlay' : 'toast';
}

/**
 * `CANCELED` is a refund rather than a loss: it means nothing could be graded,
 * and the entry came back.
 */
export function outcomeOf(item: ActivityItem): SettlementOutcome {
  if (item.state === 'CANCELED') return 'refund';
  if (item.state === 'PUSHED') return 'push';
  if (item.type === 'tournament') return tournamentPrize(item) > 0 ? 'win' : 'loss';
  const net = item.net_cents ?? 0;
  if (net > 0) return 'win';
  if (net < 0) return 'loss';
  return 'push';
}

function tournamentPrize(item: ActivityItem): number {
  return (
    item.detail?.prize_cents ??
    Math.max(0, (item.net_cents ?? 0) + item.entry_cents)
  );
}

function loadAnnounced(): Set<string> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? new Set(parsed.map(String)) : new Set();
  } catch {
    return new Set();
  }
}

function saveAnnounced(ids: Set<string>): void {
  try {
    const trimmed = Array.from(ids).slice(-MAX_REMEMBERED);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // Private mode / quota.
  }
}

function useHasAttention(): boolean {
  const read = () =>
    typeof document === 'undefined' || document.visibilityState !== 'hidden';

  const [attentive, setAttentive] = useState(read);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const sync = () => setAttentive(read());
    document.addEventListener('visibilitychange', sync);
    window.addEventListener('focus', sync);
    window.addEventListener('blur', sync);
    sync();
    return () => {
      document.removeEventListener('visibilitychange', sync);
      window.removeEventListener('focus', sync);
      window.removeEventListener('blur', sync);
    };
  }, []);

  return attentive;
}

export function useSettlementCelebration(): {
  current: Settlement | null;
  dismiss: () => void;
  claim: (id: string) => () => void;
} {
  const { data } = useActivity();
  const attentive = useHasAttention();
  const [queue, setQueue] = useState<Settlement[]>([]);
  const announced = useRef<Set<string> | null>(null);
  const seeded = useRef(false);
  // Contests a screen is already showing the result of (the match stage).
  const claimed = useRef(new Set<string>());

  useEffect(() => {
    if (!data) return;
    if (!attentive) return;
    const items: ActivityItem[] = data.items ?? [];
    if (announced.current === null) announced.current = loadAnnounced();
    const seen = announced.current;

    const terminal = items.filter((i) => TERMINAL.has(i.state));

    if (!seeded.current) {
      seeded.current = true;
      const now = Date.now();
      const justHappened = (i: ActivityItem) => {
        if (seen.has(i.id)) return false;
        if (!i.resolved_at) return false;
        const at = Date.parse(i.resolved_at);
        return Number.isFinite(at) && now - at <= RECENT_MS;
      };
      const arrivals = terminal.filter(justHappened);
      for (const item of terminal) {
        if (!arrivals.includes(item)) seen.add(item.id);
      }
      saveAnnounced(seen);
      if (arrivals.length === 0) return;
      enqueue(arrivals, seen);
      return;
    }

    const fresh = terminal.filter((i) => !seen.has(i.id));
    if (fresh.length === 0) return;
    enqueue(fresh, seen);

    function enqueue(items_: ActivityItem[], seen_: Set<string>) {
      for (const item of items_) seen_.add(item.id);
      saveAnnounced(seen_);

      const ordered = items_
        .filter((i) => !claimed.current.has(i.id))
        .sort((a, b) => (a.resolved_at ?? '').localeCompare(b.resolved_at ?? ''))
        .slice(-MAX_BURST);

      setQueue((q) => [
        ...q,
        ...ordered.map((item) => ({
          id: item.id,
          outcome: outcomeOf(item),
          netCents: item.net_cents ?? 0,
          amountCents:
            item.type === 'tournament'
              ? tournamentPrize(item)
              : Math.abs(item.net_cents ?? 0),
          balanceDeltaCents:
            item.type === 'tournament'
              ? tournamentPrize(item)
              : (item.net_cents ?? 0),
          title: item.title ?? item.market_label,
          game: item.game,
          type: item.type,
          entryCents: item.entry_cents,
          prizeCents: item.detail?.prize_cents,
          opponent: item.opponent_username,
          termination: item.detail?.termination ?? null,
        })),
      ]);
    }
  }, [data, attentive]);

  const dismiss = useCallback(() => setQueue((q) => q.slice(1)), []);
  const claim = useCallback((id: string) => {
    claimed.current.add(id);
    setQueue((q) => (q.some((s) => s.id === id) ? q.filter((s) => s.id !== id) : q));
    return () => {
      claimed.current.delete(id);
    };
  }, []);

  return { current: queue[0] ?? null, dismiss, claim };
}
