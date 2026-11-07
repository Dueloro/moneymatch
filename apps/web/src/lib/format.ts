// No odds anywhere: we show entries, pots, prizes, and rake.

/** 1 point = 1 internal cent unit. Points are whole numbers, no cash value. */
export function formatPointsValue(cents: number): string {
  const n = Math.trunc(cents);
  const abs = Math.abs(n).toLocaleString('en-US');
  return n < 0 ? `-${abs}` : abs;
}

/** "1,000 pts" in compact UI; `long` gives "1,000 points" for sentences. */
export function formatPoints(cents: number, { long = false } = {}): string {
  const unit = long ? (Math.abs(Math.trunc(cents)) === 1 ? 'point' : 'points') : 'pts';
  return `${formatPointsValue(cents)} ${unit}`;
}

export function formatSignedPoints(cents: number): string {
  if (cents > 0) return `+${formatPoints(cents)}`;
  return formatPoints(cents);
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
