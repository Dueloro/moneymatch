// No odds anywhere: we show entries, pots, prizes, and rake.

export function formatCurrency(cents: number): string {
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(Math.trunc(cents));
  const dollars = Math.floor(abs / 100).toLocaleString('en-US');
  const remainder = String(abs % 100).padStart(2, '0');
  return `${sign}$${dollars}.${remainder}`;
}

export function formatSignedCurrency(cents: number): string {
  if (cents > 0) return `+${formatCurrency(cents)}`;
  return formatCurrency(cents);
}

export function dashless(text: string): string {
  return text
    .replace(/\s*[—–]\s*/g, ' · ')
    .replace(/\s*·\s*·\s*/g, ' · ')
    .trim();
}

export function formatPct(prob: number): string {
  return `${Math.round(prob * 100)}%`;
}

export function formatStat(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

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
