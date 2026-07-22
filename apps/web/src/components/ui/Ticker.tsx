import { formatCurrency } from '../../lib/format';
import { useWaiting } from '../../hooks/useMatchmaking';

/**
 * Live activity crawl fed by real players currently waiting for a match (across
 * all games). Honest liveness — it renders nothing when no one is waiting, so we
 * never fabricate activity (design system: no seeded/bot content).
 */
export function Ticker() {
  const { data } = useWaiting(undefined);
  const items = data?.waiting ?? [];
  if (items.length === 0) return null;

  const row = (key: string, w: (typeof items)[number]) => (
    <span key={key} className="mx-5 inline-flex items-center gap-2 text-xs">
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-green" aria-hidden />
      <span className="font-semibold text-text">{w.username ?? 'A player'}</span>
      <span className="text-text-secondary">wants {w.market_label}</span>
      <span className="font-semibold text-text">{formatCurrency(w.entry_cents)}</span>
    </span>
  );

  return (
    <div
      className="relative overflow-hidden border-b border-hairline py-2.5"
      data-testid="live-ticker"
      aria-label="Players looking for a match"
    >
      <div className="flex w-max animate-marquee whitespace-nowrap">
        {items.map((w, i) => row(`a-${w.ticket_id}-${i}`, w))}
        {items.map((w, i) => row(`b-${w.ticket_id}-${i}`, w))}
      </div>
    </div>
  );
}
