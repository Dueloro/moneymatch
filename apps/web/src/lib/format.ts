// Display formatters. Ported from poc-reference/utils/format.ts and switched to
// integer cents (the server owns every number as cents — 04-phase-1 design
// rules). No odds anywhere: we show entries, pots, prizes, and rake.

/** Format integer cents as USD, e.g. 102394 → "$1,023.94". Exact integer math. */
export function formatCurrency(cents: number): string {
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(Math.trunc(cents));
  const dollars = Math.floor(abs / 100).toLocaleString('en-US');
  const remainder = String(abs % 100).padStart(2, '0');
  return `${sign}$${dollars}.${remainder}`;
}

/** Like `formatCurrency` but always shows the sign, e.g. 1800 → "+$18.00". */
export function formatSignedCurrency(cents: number): string {
  if (cents > 0) return `+${formatCurrency(cents)}`;
  return formatCurrency(cents); // negative already carries "-", zero is "$0.00"
}

/** Format a probability / share (0..1) as a whole-number percentage. */
export function formatPct(prob: number): string {
  return `${Math.round(prob * 100)}%`;
}

/** Compact relative time for ledger rows, e.g. "just now", "5m ago", "3d ago". */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((now.getTime() - new Date(iso).getTime()) / 1000);
  if (seconds < 45) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
