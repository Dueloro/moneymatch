import type { Contract, Objective } from '../types';

/** One-line plain-English description of what decides the contest. */
export function objectiveDetail(o: Objective, opponent?: string): string {
  const who = opponent ? ` to beat ${opponent}` : '';
  switch (o.kind) {
    case 'win_under_moves':
      return `Win your next qualifying game in under ${o.moves} moves${who}.`;
    case 'win_h2h':
    default:
      return `Win your next qualifying game${who}. Winner takes the pot, minus rake.`;
  }
}

export function windowLabel(hours: number): string {
  if (hours % 24 === 0) {
    const d = hours / 24;
    return `${d} day${d > 1 ? 's' : ''}`;
  }
  return `${hours}h`;
}

/** Remaining time on a contest window, e.g. "3h 12m left" / "Window closed". */
export function timeLeftLabel(matchedAt: number, windowHours: number, now: number): string {
  const end = matchedAt + windowHours * 3_600_000;
  const ms = end - now;
  if (ms <= 0) return 'Window closed';
  const totalMin = Math.floor(ms / 60_000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h left`;
  if (h > 0) return `${h}h ${m}m left`;
  return `${m}m left`;
}

export function outcomeBadge(c: Contract): { variant: string; label: string } {
  if (c.outcome === 'won') return { variant: 'won', label: 'Won' };
  if (c.outcome === 'lost') return { variant: 'lost', label: 'Lost' };
  if (c.outcome === 'refunded') return { variant: 'phase', label: 'Refunded' };
  if (c.state === 'RESOLVING') return { variant: 'pending', label: 'Resolving' };
  return { variant: 'pending', label: 'Live' };
}

/** Tone for the matchmaking quality chip. */
export function matchQualityTone(quality: number): string {
  if (quality >= 0.8) return 'var(--pos)';
  if (quality >= 0.5) return 'var(--amber)';
  return 'var(--crimson)';
}
