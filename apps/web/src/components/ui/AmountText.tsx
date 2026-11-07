import { formatCurrency, formatSignedCurrency } from '../../lib/format';

/**
 * Every money figure goes through here (or AnimatedBalance) so it gets the
 * numeric face. `signed` shows an explicit + on positives (ledger rows); off
 * for plain balances. `money` is always lime (a balance, a payout to come).
 */
export function AmountText({
  cents,
  signed = true,
  win = false,
  money = false,
  className = '',
  testId,
}: {
  cents: number;
  signed?: boolean;
  win?: boolean;
  money?: boolean;
  className?: string;
  testId?: string;
}) {
  const color =
    money || (win && cents > 0)
      ? 'text-green'
      : cents < 0
        ? 'text-text-secondary'
        : 'text-text';
  const text = signed ? formatSignedCurrency(cents) : formatCurrency(cents);
  return (
    <span className={`num ${color} ${className}`} data-testid={testId}>
      {text}
    </span>
  );
}
