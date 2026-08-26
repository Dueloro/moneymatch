import { useCallback, useEffect, useRef, useState } from 'react';

import type { ActivityItem } from './useActivity';
import { useActivity } from './useActivity';

/**
 * Notices the moment one of your contests settles, so the result can be shown
 * rather than merely appearing in a list.
 *
 * Settlement is the moment the product does its job, and until now it arrived
 * silently: a row in Activity changed state while you were probably looking at
 * a different page. This watches for the transition itself.
 *
 * There is no settlement event on the wire to listen for — `/events/stream`
 * pushes a bare ping and the client refetches — so the transition is detected
 * by diffing successive Activity snapshots. That is deliberate rather than a
 * workaround: it fires for any route to settlement (worker, admin resettle, a
 * dispute resolution) instead of only the one path that happened to emit an
 * event.
 *
 * Two properties that make it trustworthy:
 *
 * - **A contest is announced once, ever.** Ids that have been shown are kept in
 *   `localStorage`, so a refresh, a second tab, or a returning visit does not
 *   replay results you have already seen.
 * - **A result that landed while you were away is still shown**, provided it is
 *   recent and has not been announced before. This is the case that matters
 *   most and the one the first version got wrong: **you have to leave this app
 *   to play.** Chess happens on lichess.org, CS2 in a desktop client. So you
 *   are, almost by definition, not looking at Money Match at the moment your
 *   contest settles. Firing only on a transition an open tab happened to
 *   witness meant the real path — go play, come back — showed nothing at all.
 * - **Nothing is announced to a tab nobody is looking at.** This is the subtler
 *   half of the same problem. `useEventStream` invalidates `['activity']` the
 *   instant the worker settles, and an explicit invalidation refetches whether
 *   or not the tab is in front. So a backgrounded tab would detect the
 *   settlement, play the whole sequence to nobody, mark the contest announced
 *   and never show it again — the result was *consumed* while you were on
 *   lichess.org. Detection is therefore held, along with the announced-marking
 *   it implies, until the tab is visible (`visibilityState !== 'hidden'`)
 *   rather than backgrounded.
 *
 * Everything terminal but older than `RECENT_MS` is recorded silently, so
 * opening the app after a week does not replay your history at you.
 */

/**
 * Bumped from v1: the previous behaviour marked contests announced from a
 * backgrounded tab, so any browser that ran it is carrying ids for results it
 * never actually showed. Those would stay suppressed forever. A new key
 * releases them; the `RECENT_MS` window on first load keeps that from turning
 * into a replay of your whole history.
 */
const STORAGE_KEY = 'mm.announced-settlements.v2';

/** Terminal states, matching `ActivityCard`'s own set. */
const TERMINAL = new Set(['SETTLED', 'PUSHED', 'CANCELED']);

/** Cap the stored id list so it cannot grow without bound. */
const MAX_REMEMBERED = 400;

/**
 * Most sequences played back-to-back from a single batch.
 *
 * A tab left open for a long weekend can come back to a pile of settled
 * contests, and every sequence is a full-screen takeover: twelve of them is
 * twenty-odd seconds of hijacked screen. Older ones are still marked announced,
 * they just are not performed.
 */
const MAX_BURST = 3;

/**
 * How recently a contest must have resolved to be worth announcing on arrival.
 *
 * This has to cover *playing an entire game elsewhere with this tab closed*,
 * which sets the floor much higher than it first appears: a CS2 Premier match
 * runs 40 minutes and a slow chess game is not far behind. Ten minutes — the
 * first guess — expired mid-match and swallowed exactly the results it existed
 * to show. An hour covers a full session and is still unambiguously "just now";
 * yesterday's history stays silent either way. Compared against the browser
 * clock, so it is deliberately generous about skew.
 */
const RECENT_MS = 60 * 60 * 1000;

export type SettlementOutcome = 'win' | 'loss' | 'push' | 'refund';

export interface Settlement {
  id: string;
  outcome: SettlementOutcome;
  netCents: number;
  title: string;
  game: string;
  /** `pool` | `tournament` | `match` — drives the wording. */
  type: ActivityItem['type'];
}

/**
 * Which of the four results this is.
 *
 * `CANCELED` is a refund rather than a loss: it means nothing could be graded,
 * and the entry came back. Telling a player they lost when they were refunded
 * would be worse than saying nothing.
 */
export function outcomeOf(item: ActivityItem): SettlementOutcome {
  if (item.state === 'CANCELED') return 'refund';
  if (item.state === 'PUSHED') return 'push';
  const net = item.net_cents ?? 0;
  if (net > 0) return 'win';
  if (net < 0) return 'loss';
  return 'push';
}

function loadAnnounced(): Set<string> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? new Set(parsed.map(String)) : new Set();
  } catch {
    // A corrupt or unavailable store must not break the app. Worst case a
    // result is announced twice, which is far better than a crash on load.
    return new Set();
  }
}

function saveAnnounced(ids: Set<string>): void {
  try {
    const trimmed = Array.from(ids).slice(-MAX_REMEMBERED);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // Private mode / quota. Nothing to do; the in-memory set still holds for
    // this session, which is the case that matters.
  }
}

/**
 * Whether the tab is on screen, so a result drawn now would actually be seen.
 *
 * The one case worth holding for is the tab you *left* — backgrounded or
 * minimised while you go play the game elsewhere — and `visibilityState`
 * reports exactly that: `hidden`. A visible tab is on screen and can be shown
 * to.
 *
 * An earlier version also required `document.hasFocus()`, meaning to also hold
 * a visible-but-unfocused tab (say, one sitting behind the window you are
 * playing in). In practice that check is too sharp and fails the common case:
 * `hasFocus()` is false whenever the page is not the OS-frontmost surface — the
 * devtools pane is focused, another app is in front, the tab is embedded in a
 * webview. Settlement usually lands while you are doing precisely one of those
 * (you leave this app to play), so gating on focus held the result forever and
 * the sequence never played. Visibility is the honest signal; a rare overlay
 * shown to a visible tab you happen not to be staring at is a far smaller cost
 * than never showing it at all.
 *
 * `focus`/`blur` are still listened to: they are cheap re-check triggers for
 * the browsers that fire them alongside a visibility change.
 */
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
    // The state can have moved between first render and this effect running.
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
} {
  const { data } = useActivity();
  const attentive = useHasAttention();
  const [queue, setQueue] = useState<Settlement[]>([]);
  const announced = useRef<Set<string> | null>(null);
  const seeded = useRef(false);

  useEffect(() => {
    if (!data) return;
    // Hold everything — including marking contests announced — until this tab
    // is the one being looked at. Detecting a settlement in a background tab
    // would spend the result on an empty room: the sequence plays out, the id
    // is recorded as shown, and the one moment worth showing is gone. Whatever
    // arrived while away is still in `data` when attention returns, so nothing
    // is lost by waiting.
    if (!attentive) return;
    const items: ActivityItem[] = data.items ?? [];
    if (announced.current === null) announced.current = loadAnnounced();
    const seen = announced.current;

    const terminal = items.filter((i) => TERMINAL.has(i.state));

    // First snapshot: anything that resolved *just now* is still worth showing —
    // you were away playing the game. Everything older is recorded silently.
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

      // Oldest first, so a burst is shown in the order the contests resolved,
      // keeping the most recent few if a long absence produced a pile.
      const ordered = [...items_]
        .sort((a, b) => (a.resolved_at ?? '').localeCompare(b.resolved_at ?? ''))
        .slice(-MAX_BURST);

      setQueue((q) => [
        ...q,
        ...ordered.map((item) => ({
          id: item.id,
          outcome: outcomeOf(item),
          netCents: item.net_cents ?? 0,
          title: item.title ?? item.market_label,
          game: item.game,
          type: item.type,
        })),
      ]);
    }
  }, [data, attentive]);

  const dismiss = useCallback(() => setQueue((q) => q.slice(1)), []);

  return { current: queue[0] ?? null, dismiss };
}
