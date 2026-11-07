import { formatPoints } from './format';

// Display-only mirror of the server's rake (apps/api services/money_math.py:
// DEFAULT_RAKE_BPS).
export const RAKE_BPS = 1000;

export function rakeOnPot(potCents: number): number {
  return Math.floor((potCents * RAKE_BPS) / 10000);
}

/**
 * The fee implied by a *net* payout figure (an est. pool share is already net
 * of rake).
 */
export function feeOnNetWinnings(netCents: number): number {
  return Math.floor((netCents * RAKE_BPS) / (10000 - RAKE_BPS));
}

export function platformFeeNote(feeCents: number): string {
  return `Fee ${formatPoints(feeCents)}`;
}
