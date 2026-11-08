import { formatPoints } from '../../lib/format';
import { lookingFor } from '../../lib/tickerCopy';
import { useWaiting } from '../../hooks/useMatchmaking';

export function Ticker() {
  const { data } = useWaiting(undefined);
  const items = data?.waiting ?? [];
  if (items.length === 0) return null;

  const row = (key: string, w: (typeof items)[number]) => (
    <span key={key} className="mx-5 inline-flex items-center gap-2 text-xs">
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-live" aria-hidden />
      <span className="font-medium text-text">{w.username ?? 'A player'}</span>
      <span className="text-text-secondary">{lookingFor(w.speed)}</span>
      <span aria-hidden className="text-text-tertiary">
        ·
      </span>
      <span className="font-medium text-text">{formatPoints(w.entry_cents)}</span>
    </span>
  );

  return (
    <div
      className="no-scrollbar relative overflow-hidden border-b border-hairline py-2.5"
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
