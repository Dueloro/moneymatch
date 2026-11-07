import { formatCurrency, formatSignedCurrency } from '../../lib/format';

/**
 * `signed` shows an explicit + on positives (ledger rows); off for plain
 * balances.
 */
export function AmountText({
  cents,
  signed = true,
  win = false,
  className = '',
}: {
  cents: number;
  signed?: boolean;
  win?: boolean;
  className?: string;
}) {
  const color =
    win && cents > 0 ? 'text-green' : cents < 0 ? 'text-text-secondary' : 'text-text';
  const text = signed ? formatSignedCurrency(cents) : formatCurrency(cents);
  return <span className={`tabular-nums ${color} ${className}`}>{text}</span>;
}
