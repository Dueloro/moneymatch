import { useEffect, useMemo, useRef, useState } from 'react';

import { AmountText } from '../components/ui/AmountText';
import { EmptyState } from '../components/ui/EmptyState';
import { ListRow } from '../components/ui/ListRow';
import { PillButton } from '../components/ui/PillButton';
import { formatCurrency, formatRelativeTime } from '../lib/format';
import { statValue, useActivity, type ActivityItem } from '../hooks/useActivity';
import { useCreateChallenge } from '../hooks/useChallenges';

const LIVE_STATES = new Set(['ACTIVE', 'AWAITING_RESULT']);
const TERMINAL_STATES = new Set(['SETTLED', 'PUSHED', 'CANCELED']);

/** A win or a live contest gets the green dot; everything settled is gray. */
function dotClass(item: ActivityItem): string {
  const won = item.state === 'SETTLED' && (item.net_cents ?? 0) > 0;
  const live = LIVE_STATES.has(item.state) || item.state === 'LOCKED';
  return won || live ? 'bg-green' : 'bg-text-secondary';
}

function stateLabel(item: ActivityItem): string {
  switch (item.state) {
    case 'PENDING':
      return 'Awaiting confirmation';
    case 'ACTIVE':
    case 'AWAITING_RESULT':
    case 'OPEN':
    case 'LOCKED':
      return 'In progress';
    case 'PUSHED':
      return 'Push · refunded';
    case 'CANCELED':
      return 'Refunded';
    case 'SETTLED':
      if ((item.net_cents ?? 0) > 0) return 'Won';
      return (item.net_cents ?? 0) < 0 ? 'Lost' : 'Settled';
    default:
      return item.state;
  }
}

/** Stat-race result line (matches only — pools/tournaments have no opponent). */
function statLine(item: ActivityItem): string | null {
  if (item.type !== 'match') return null;
  const you = statValue(item.your_stat_line);
  const opp = statValue(item.opponent_stat_line);
  if (you == null && opp == null) return null;
  const name = item.opponent_username ?? 'opponent';
  return `You ${you ?? '—'} · ${name} ${opp ?? '—'}`;
}

function title(item: ActivityItem): string {
  if (item.title) return item.title;
  return `vs ${item.opponent_username ?? 'opponent'} · ${item.market_label}`;
}

/** A newly-settled contest → a one-line toast summarizing the outcome. */
function toastFor(item: ActivityItem): string {
  const what =
    item.type === 'match'
      ? `vs ${item.opponent_username ?? 'opponent'}`
      : (item.title ?? item.market_label);
  const net = item.net_cents ?? 0;
  if (item.state === 'SETTLED') {
    if (net > 0) return `You won ${formatCurrency(net)} ${what}`;
    if (net < 0) return `You lost ${formatCurrency(Math.abs(net))} ${what}`;
    return `Settled — ${what}`;
  }
  if (item.state === 'PUSHED') return `Push ${what} — entry refunded`;
  return `Refunded — ${what}`;
}

/** One-tap rematch on a settled H2H row → challenge the same opponent
 * (08-phase-5 · deliverable 6). */
function RematchButton({
  item,
  onSent,
}: {
  item: ActivityItem;
  onSent: (msg: string) => void;
}) {
  const rematch = useCreateChallenge();
  if (item.type !== 'match' || !TERMINAL_STATES.has(item.state)) return null;
  return (
    <PillButton
      variant="outline"
      disabled={rematch.isPending}
      onClick={async () => {
        try {
          await rematch.mutateAsync({ rematch_of: item.id });
          onSent(`Rematch sent to ${item.opponent_username ?? 'opponent'}`);
        } catch (e) {
          onSent((e as Error).message);
        }
      }}
    >
      Rematch
    </PillButton>
  );
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
                  <div className="flex items-center gap-3">
                    {item.net_cents != null ? (
                      <AmountText cents={item.net_cents} win={item.net_cents > 0} />
                    ) : (
                      <span className="text-xs text-text-secondary">
                        {formatCurrency(item.entry_cents)} in play
                      </span>
                    )}
                    <RematchButton item={item} onSent={setToast} />
                  </div>
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
