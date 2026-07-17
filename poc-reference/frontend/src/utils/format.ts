// Display formatters for money match. No odds: the platform is peer-to-peer and
// shows entries, pots, prizes, and rake — never a payout line.

const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatCurrency(amount: number): string {
  return currency.format(amount);
}

/** Format a probability / share (0..1) as a whole-number percentage. */
export function formatPct(prob: number): string {
  return `${Math.round(prob * 100)}%`;
}
