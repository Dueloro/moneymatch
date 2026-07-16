import { useEffect, useMemo, useRef, useState } from 'react';

import { AmountText } from '../components/ui/AmountText';
import { EmptyState } from '../components/ui/EmptyState';
import { ListRow } from '../components/ui/ListRow';
import { formatCurrency, formatRelativeTime } from '../lib/format';
import { statValue, useActivity, type ActivityItem } from '../hooks/useActivity';

const LIVE_STATES = new Set(['ACTIVE', 'AWAITING_RESULT']);

/** Won matches and live matches get the green dot; everything settled is gray. */
function dotClass(item: ActivityItem): string {
  const won = item.state === 'SETTLED' && (item.net_cents ?? 0) > 0;
  const live = LIVE_STATES.has(item.state);
  return won || live ? 'bg-green' : 'bg-text-secondary';
}

function stateLabel(item: ActivityItem): string {
  switch (item.state) {
    case 'PENDING':
      return 'Awaiting confirmation';
    case 'ACTIVE':
    case 'AWAITING_RESULT':
      return 'In progress';
    case 'PUSHED':
      return 'Push · refunded';
    case 'CANCELED':
      return 'Refunded';
    case 'SETTLED':
      return (item.net_cents ?? 0) > 0 ? 'Won' : 'Lost';
  }
}

function statLine(item: ActivityItem): string | null {
  const you = statValue(item.your_stat_line);
  const opp = statValue(item.opponent_stat_line);
  if (you == null && opp == null) return null;
  const name = item.opponent_username ?? 'opponent';
  return `You ${you ?? '—'} · ${name} ${opp ?? '—'}`;
}

function title(item: ActivityItem): string {
  return `vs ${item.opponent_username ?? 'opponent'} · ${item.market_label}`;
}

/** A newly-settled match → a one-line toast summarizing the outcome. */
function toastFor(item: ActivityItem): string {
  const name = item.opponent_username ?? 'opponent';
  if (item.state === 'SETTLED') {
    const net = item.net_cents ?? 0;
    return net > 0
      ? `You won ${formatCurrency(net)} vs ${name}`
      : `You lost ${formatCurrency(Math.abs(net))} vs ${name}`;
  }
  if (item.state === 'PUSHED') return `Push vs ${name} — entry refunded`;
  return `Match vs ${name} refunded`;
}

export function ActivityPage() {
  const { data, isLoading } = useActivity();
  const items = useMemo(() => data?.items ?? [], [data]);

  // Settlement toast: track which resolved matches we've already shown, seeding
  // from the first load so we only pop for transitions that happen live.
  const seen = useRef<Set<string> | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    const resolved = items.filter((i) => i.resolved_at != null);
    if (seen.current === null) {
      seen.current = new Set(resolved.map((i) => i.id));
      return;
    }
    const fresh = resolved.find((i) => !seen.current!.has(i.id));
    if (fresh) {
      resolved.forEach((i) => seen.current!.add(i.id));
      setToast(toastFor(fresh));
    }
  }, [items]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <div className="max-w-2xl">
      <h1 className="mb-6 text-2xl font-bold">Activity</h1>

      {isLoading ? (
        <p className="text-sm text-text-secondary">Loading…</p>
      ) : items.length === 0 ? (
        <EmptyState
          title="Nothing here yet"
          subline="Your matches, pools, and tournaments will show up here."
        />
      ) : (
        <div>
          {items.map((item) => {
            const sub = statLine(item);
            return (
              <ListRow
                key={item.id}
                left={
                  <span
                    aria-hidden
                    className={`h-2.5 w-2.5 rounded-full ${dotClass(item)}`}
                  />
                }
                title={title(item)}
                subline={
                  <>
                    {stateLabel(item)}
                    {sub && <span className="text-text-secondary"> · {sub}</span>}
                    {item.resolved_at && (
                      <span className="text-text-secondary">
                        {' '}
                        · {formatRelativeTime(item.resolved_at)}
                      </span>
                    )}
                  </>
                }
                right={
                  item.net_cents != null ? (
                    <AmountText cents={item.net_cents} win={item.net_cents > 0} />
                  ) : (
                    <span className="text-xs text-text-secondary">
                      {formatCurrency(item.entry_cents)} in play
                    </span>
                  )
                }
              />
            );
          })}
        </div>
      )}

      {toast && (
        <div
          role="status"
          data-testid="settlement-toast"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-pill bg-panel-raised px-5 py-3 text-sm font-semibold text-text shadow-lg"
        >
          {toast}
        </div>
      )}
    </div>
  );
}
