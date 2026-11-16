import { formatPoints } from './format';

// Display only. `rakeBps` comes from the server (`useConfig`), never a local copy.
export function rakeOnPot(potCents: number, rakeBps: number): number {
  return Math.floor((potCents * rakeBps) / 10000);
}

/**
 * The fee implied by a *net* payout figure (an est. pool share is already net
 * of rake).
 */
export function feeOnNetWinnings(netCents: number, rakeBps: number): number {
  return Math.floor((netCents * rakeBps) / (10000 - rakeBps));
}

export function platformFeeNote(feeCents: number): string {
  return `Fee ${formatPoints(feeCents)}`;
}
