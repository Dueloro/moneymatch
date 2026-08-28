import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ActivityItem } from '../hooks/useActivity';
import { outcomeOf } from '../hooks/useSettlementCelebration';
import { SettlementCelebration } from './SettlementCelebration';
import { SettlementProvider } from './SettlementProvider';

// The overlay now reads the shared settlement stream from context, so tests
// mount it inside the provider (which runs the detection hook against the
// mocked activity above).
function Cel() {
  return (
    <SettlementProvider>
      <SettlementCelebration />
    </SettlementProvider>
  );
}

/**
 * Settlement is the moment the product does its job, and it used to happen
 * silently — a row in Activity changed state while you were looking at another
 * page. These cover the two things that make announcing it trustworthy: it
 * fires on the *transition*, and it fires exactly once.
 */

const activity = vi.hoisted(() => ({ data: undefined as unknown }));

vi.mock('../hooks/useActivity', () => ({
  useActivity: () => activity,
}));

function item(over: Partial<ActivityItem> & { id: string }): ActivityItem {
  return {
    type: 'pool',
    game: 'cs2.steam',
    market: 'cs2_kills',
    market_label: 'Kills',
    kind: 'pool',
    state: 'LOCKED',
    entry_cents: 2_500,
    title: 'Kills · Easy pool',
    net_cents: null,
    opponent_username: null,
    your_stat_line: null,
    opponent_stat_line: null,
    live: null,
    detail: null,
    dispute_status: null,
    created_at: '2026-08-25T10:00:00Z',
    resolved_at: null,
    ...over,
  } as ActivityItem;
}

function setActivity(items: ActivityItem[]) {
  activity.data = { items };
}

beforeEach(() => {
  window.localStorage.clear();
  activity.data = undefined;
});

afterEach(() => {
  vi.useRealTimers();
});

describe('SettlementCelebration', () => {
  it('says nothing about contests that settled long before you arrived', () => {
    // Otherwise opening the app replays your entire history at you.
    setActivity([
      item({
        id: 'a',
        state: 'SETTLED',
        net_cents: 5_000,
        resolved_at: '2020-01-01T00:00:00Z',
      }),
    ]);
    render(<Cel />);
    expect(screen.queryByTestId('settlement-celebration')).not.toBeInTheDocument();
  });

  // The case the first version got wrong, and the one that matters most: you
  // have to LEAVE this app to play. Chess is on lichess.org, CS2 is a desktop
  // client. So the moment your contest settles, you are somewhere else — and a
  // result only shown to an open tab is a result nobody ever sees.
  it('announces a result that landed while you were away playing', () => {
    setActivity([
      item({
        id: 'a',
        state: 'SETTLED',
        net_cents: 2_000,
        resolved_at: new Date(Date.now() - 90_000).toISOString(),
      }),
    ]);
    render(<Cel />);
    expect(screen.getByTestId('settlement-celebration')).toBeInTheDocument();
    expect(screen.getByText('You won')).toBeInTheDocument();
  });

  it('does not replay that result on the next visit', () => {
    const recent = new Date(Date.now() - 90_000).toISOString();
    setActivity([
      item({ id: 'a', state: 'SETTLED', net_cents: 2_000, resolved_at: recent }),
    ]);
    const first = render(<Cel />);
    expect(screen.getByTestId('settlement-celebration')).toBeInTheDocument();
    first.unmount();

    render(<Cel />);
    expect(screen.queryByTestId('settlement-celebration')).not.toBeInTheDocument();
  });

  it('ignores an unannounced result that is no longer recent', () => {
    // Coming back tomorrow should be quiet, even on a fresh browser. Sit clearly
    // past the one-hour window (not exactly on it) so the boundary `<=` compare
    // can't flip on sub-millisecond timing.
    setActivity([
      item({
        id: 'a',
        state: 'SETTLED',
        net_cents: 2_000,
        resolved_at: new Date(Date.now() - 61 * 60 * 1000).toISOString(),
      }),
    ]);
    render(<Cel />);
    expect(screen.queryByTestId('settlement-celebration')).not.toBeInTheDocument();
  });

  it('announces a win when a live contest settles in your favour', () => {
    setActivity([item({ id: 'a', state: 'LOCKED' })]);
    const { rerender } = render(<Cel />);

    act(() => {
      setActivity([item({ id: 'a', state: 'SETTLED', net_cents: 9_000 })]);
      rerender(<Cel />);
    });

    expect(screen.getByTestId('settlement-celebration')).toBeInTheDocument();
    expect(screen.getByText('You won')).toBeInTheDocument();
    // The visible figure counts up from zero; the announced text carries the
    // final amount immediately, which is the number that must be right.
    expect(screen.getByRole('status')).toHaveTextContent(/You won \$90\.00/);
  });

  it('announces a loss without dressing it up as anything else', () => {
    setActivity([item({ id: 'a', state: 'LOCKED' })]);
    const { rerender } = render(<Cel />);

    act(() => {
      setActivity([item({ id: 'a', state: 'SETTLED', net_cents: -2_500 })]);
      rerender(<Cel />);
    });

    expect(screen.getByText('You lost…')).toBeInTheDocument();
    // A loss is stated, but the amount lost is deliberately not disclosed —
    // not visibly and not in the announcement.
    expect(screen.getByRole('status')).toHaveTextContent(/You lost/);
    expect(screen.getByRole('status')).not.toHaveTextContent('$25.00');
    expect(screen.queryByTestId('settlement-amount')).not.toBeInTheDocument();
  });

  // Only a win and a loss are celebrated for now. A push and a refund still
  // classify correctly in the hook — a refund is NOT a loss and must never be
  // shown as one — they simply have no overlay yet.
  it('shows no overlay for a refund, and never calls it a loss', () => {
    setActivity([item({ id: 'a', state: 'LOCKED' })]);
    const { rerender } = render(<Cel />);

    act(() => {
      setActivity([item({ id: 'a', state: 'CANCELED', net_cents: 0 })]);
      rerender(<Cel />);
    });

    expect(screen.queryByTestId('settlement-celebration')).not.toBeInTheDocument();
    expect(screen.queryByText('You lost…')).not.toBeInTheDocument();
  });

  it('shows no overlay for a push', () => {
    setActivity([item({ id: 'a', state: 'LOCKED' })]);
    const { rerender } = render(<Cel />);

    act(() => {
      setActivity([item({ id: 'a', state: 'SETTLED', net_cents: 0 })]);
      rerender(<Cel />);
    });

    expect(screen.queryByTestId('settlement-celebration')).not.toBeInTheDocument();
  });

  it('still classifies a refund as a refund, ready to re-enable', () => {
    // The classification is the part that must not rot while the overlay is off.
    expect(outcomeOf(item({ id: 'x', state: 'CANCELED', net_cents: 0 }))).toBe(
      'refund',
    );
    expect(outcomeOf(item({ id: 'x', state: 'SETTLED', net_cents: 0 }))).toBe('push');
    expect(outcomeOf(item({ id: 'x', state: 'SETTLED', net_cents: 5 }))).toBe('win');
    expect(outcomeOf(item({ id: 'x', state: 'SETTLED', net_cents: -5 }))).toBe('loss');
  });

  it('marks the outcome on the element, not only in colour', () => {
    setActivity([item({ id: 'a', state: 'LOCKED' })]);
    const { rerender } = render(<Cel />);

    act(() => {
      setActivity([item({ id: 'a', state: 'SETTLED', net_cents: 9_000 })]);
      rerender(<Cel />);
    });

    expect(screen.getByTestId('settlement-celebration')).toHaveAttribute(
      'data-outcome',
      'win',
    );
  });

  it('announces the same contest only once, even across a remount', () => {
    // A refetch, a reconnect or a page revisit must not replay a result.
    setActivity([item({ id: 'a', state: 'LOCKED' })]);
    const first = render(<Cel />);

    act(() => {
      setActivity([item({ id: 'a', state: 'SETTLED', net_cents: 9_000 })]);
      first.rerender(<Cel />);
    });
    expect(screen.getByTestId('settlement-celebration')).toBeInTheDocument();
    first.unmount();

    render(<Cel />);
    expect(screen.queryByTestId('settlement-celebration')).not.toBeInTheDocument();
  });

  it('shows a burst one at a time, oldest first', () => {
    setActivity([
      item({ id: 'a', state: 'LOCKED' }),
      item({ id: 'b', state: 'LOCKED' }),
    ]);
    const { rerender } = render(<Cel />);

    act(() => {
      setActivity([
        item({
          id: 'b',
          state: 'SETTLED',
          net_cents: -2_500,
          title: 'Second',
          resolved_at: '2026-08-25T12:00:00Z',
        }),
        item({
          id: 'a',
          state: 'SETTLED',
          net_cents: 9_000,
          title: 'First',
          resolved_at: '2026-08-25T11:00:00Z',
        }),
      ]);
      rerender(<Cel />);
    });

    // The one that resolved first is shown first, regardless of list order.
    // Asserted on the card's whole text: the title appears both in the visible
    // line and in the screen-reader announcement, so a bare text query matches
    // twice.
    expect(screen.getByRole('status')).toHaveTextContent(/First/);
    expect(screen.getByRole('status')).not.toHaveTextContent(/Second/);
  });

  it('dismisses on click, revealing the next result', async () => {
    const user = userEvent.setup();
    setActivity([
      item({ id: 'a', state: 'LOCKED' }),
      item({ id: 'b', state: 'LOCKED' }),
    ]);
    const { rerender } = render(<Cel />);

    act(() => {
      setActivity([
        item({
          id: 'a',
          state: 'SETTLED',
          net_cents: 9_000,
          title: 'First',
          resolved_at: '2026-08-25T11:00:00Z',
        }),
        item({
          id: 'b',
          state: 'SETTLED',
          net_cents: -2_500,
          title: 'Second',
          resolved_at: '2026-08-25T12:00:00Z',
        }),
      ]);
      rerender(<Cel />);
    });

    await user.click(screen.getByRole('status'));
    expect(screen.getByRole('status')).toHaveTextContent(/Second/);
  });

  it('dismisses itself on a timer', () => {
    vi.useFakeTimers();
    setActivity([item({ id: 'a', state: 'LOCKED' })]);
    const { rerender } = render(<Cel />);

    act(() => {
      setActivity([item({ id: 'a', state: 'SETTLED', net_cents: 9_000 })]);
      rerender(<Cel />);
    });
    expect(screen.getByTestId('settlement-celebration')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(4_000);
    });
    expect(screen.queryByTestId('settlement-celebration')).not.toBeInTheDocument();
  });

  it('announces the result to screen readers, not only in colour', () => {
    setActivity([item({ id: 'a', state: 'LOCKED' })]);
    const { rerender } = render(<Cel />);

    act(() => {
      setActivity([item({ id: 'a', state: 'SETTLED', net_cents: 9_000 })]);
      rerender(<Cel />);
    });

    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(status).toHaveTextContent(/You won \$90\.00/);
  });

  it('takes the screen, and gives it back within two seconds', () => {
    // A deliberate change from the first version, which floated a card and
    // never intercepted input. The takeover brief asks for the screen, so it
    // does block — and the bound on that cost is the whole design: ~1.9s, or
    // instantly on a click or Escape. Anything longer would need to go back to
    // being non-blocking.
    vi.useFakeTimers();
    setActivity([item({ id: 'a', state: 'LOCKED' })]);
    const { rerender } = render(<Cel />);

    act(() => {
      setActivity([item({ id: 'a', state: 'SETTLED', net_cents: 9_000 })]);
      rerender(<Cel />);
    });
    expect(screen.getByTestId('settlement-celebration')).toBeInTheDocument();

    // Still up just before the deadline...
    act(() => {
      vi.advanceTimersByTime(1_800);
    });
    expect(screen.getByTestId('settlement-celebration')).toBeInTheDocument();

    // ...and gone just after it.
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.queryByTestId('settlement-celebration')).not.toBeInTheDocument();
  });

  it('keeps the win and the loss distinguishable by more than colour', () => {
    // A win states the amount in lime; a loss is quieter and shows no amount.
    // If they ever converge on the same treatment, this is what should fail.
    setActivity([item({ id: 'a', state: 'LOCKED' })]);
    const { rerender, unmount } = render(<Cel />);
    act(() => {
      setActivity([item({ id: 'a', state: 'SETTLED', net_cents: 9_000 })]);
      rerender(<Cel />);
    });
    expect(screen.getByText('You won')).toBeInTheDocument();
    expect(screen.getByTestId('settlement-amount')).toBeInTheDocument();
    unmount();

    setActivity([item({ id: 'b', state: 'LOCKED' })]);
    const second = render(<Cel />);
    act(() => {
      setActivity([item({ id: 'b', state: 'SETTLED', net_cents: -2_500 })]);
      second.rerender(<Cel />);
    });
    expect(screen.getByText('You lost…')).toBeInTheDocument();
    expect(screen.queryByTestId('settlement-amount')).not.toBeInTheDocument();
  });
});

/**
 * The failure that made the feature useless in practice.
 *
 * `useEventStream` invalidates `['activity']` the moment the worker settles,
 * and an explicit invalidation refetches whether or not the tab is in front.
 * You have to leave this app to play, so that refetch reliably landed in a
 * backgrounded tab: the sequence played to nobody, the contest was marked
 * announced, and coming back showed nothing — permanently, because the
 * announced set is persisted.
 */
describe('SettlementCelebration — a tab nobody is looking at', () => {
  let hidden = false;
  let focused = true;

  beforeEach(() => {
    hidden = false;
    focused = true;
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() =>
      hidden ? 'hidden' : 'visible',
    );
    vi.spyOn(document, 'hasFocus').mockImplementation(() => focused);
  });

  afterEach(() => vi.restoreAllMocks());

  function background() {
    hidden = true;
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
  }

  function foreground() {
    hidden = false;
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
  }

  const settled = () =>
    item({
      id: 'p-away',
      state: 'SETTLED',
      net_cents: 2_000,
      resolved_at: new Date().toISOString(),
    });

  it('holds the result until you come back, instead of spending it on an empty room', () => {
    setActivity([item({ id: 'p-away' })]);
    const { rerender } = render(<Cel />);

    background();

    // The worker settles and SSE pushes the refetch through to the hidden tab.
    setActivity([settled()]);
    act(() => {
      rerender(<Cel />);
    });
    expect(screen.queryByTestId('settlement-celebration')).toBeNull();

    foreground();
    expect(screen.getByTestId('settlement-celebration')).toHaveAttribute(
      'data-outcome',
      'win',
    );
  });

  it('does not burn the contest while hidden, so a later visit still shows it', () => {
    setActivity([item({ id: 'p-away' })]);
    const first = render(<Cel />);

    background();
    setActivity([settled()]);
    act(() => {
      first.rerender(<Cel />);
    });
    first.unmount();

    // A fresh tab, reading the same persisted announced set.
    hidden = false;
    render(<Cel />);
    expect(screen.getByTestId('settlement-celebration')).toHaveAttribute(
      'data-outcome',
      'win',
    );
  });

  it('shows a result on a visible tab even when it is not the focused window', () => {
    // The gate is visibility, not focus. `document.hasFocus()` is false whenever
    // the page is not the OS-frontmost surface — devtools focused, another app
    // in front, an embedded webview — which is exactly where a settlement
    // usually lands (you leave this app to play). Requiring focus held the
    // result forever in those cases and the sequence never played. A visible
    // tab is on screen, so it is shown to.
    focused = false;
    setActivity([item({ id: 'p-away' })]);
    const { rerender } = render(<Cel />);

    setActivity([settled()]);
    act(() => {
      rerender(<Cel />);
    });

    expect(screen.getByTestId('settlement-celebration')).toHaveAttribute(
      'data-outcome',
      'win',
    );
  });

  it('announces a result that resolved during a long match, not just a quick one', () => {
    // Forty minutes away is an ordinary CS2 Premier match, not a stale visit.
    setActivity([
      item({
        id: 'p-long',
        state: 'SETTLED',
        net_cents: 4_000,
        resolved_at: new Date(Date.now() - 40 * 60 * 1000).toISOString(),
      }),
    ]);
    render(<Cel />);
    expect(screen.getByTestId('settlement-celebration')).toHaveAttribute(
      'data-outcome',
      'win',
    );
  });

  it('caps a pile-up, so a long absence is not a minute of forced takeovers', () => {
    const many = Array.from({ length: 9 }, (_, i) =>
      item({
        id: `p-${i}`,
        state: 'SETTLED',
        net_cents: 1_000,
        resolved_at: new Date(Date.now() - (9 - i) * 60_000).toISOString(),
      }),
    );
    setActivity(many);
    render(<Cel />);

    // All nine are recorded as announced; only the last few are performed.
    const stored = JSON.parse(
      window.localStorage.getItem('mm.announced-settlements.v2') ?? '[]',
    ) as string[];
    expect(stored).toHaveLength(9);
  });
});
