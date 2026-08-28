import { formatCurrency } from './format';

// Display-only mirror of the server's rake (apps/api services/money_math.py:
// DEFAULT_RAKE_BPS). The server owns every settlement number; these helpers only
// build the pre-commit fee disclosure shown on browse cards, so the rake is
// always visible before a user commits (design-guidelines §8: "the rake is
// always visible pre-commit — 'winner takes $18.00 · $2.00 platform fee'").
export const RAKE_BPS = 1000; // 10%

/** Platform fee taken off a pot, in cents. Mirrors money_math.rake_for (floor). */
export function rakeOnPot(potCents: number): number {
  return Math.floor((potCents * RAKE_BPS) / 10000);
}

/**
 * The fee implied by a *net* payout figure (an est. pool share is already net of
 * rake). If net = gross · (1 − rake), the fee attributable to that payout is
 * net · rake / (1 − rake). Used where we have the net winnings but not the pot.
 */
export function feeOnNetWinnings(netCents: number): number {
  return Math.floor((netCents * RAKE_BPS) / (10000 - RAKE_BPS));
}

/**
 * The pre-commit fee subline for a card, e.g. "$2.00 platform fee". It pairs
 * with the card's payout headline (You win / Est. win / Pot if full) so the two
 * together read as the spec's "winner takes $X · $Y platform fee" without
 * repeating the payout amount directly beneath itself.
 */
export function platformFeeNote(feeCents: number): string {
  return `${formatCurrency(feeCents)} platform fee`;
}
