import { formatPointsValue } from '../../lib/format';

/**
 * Every points figure goes through here (or AnimatedBalance) so it gets the
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
  return (
    <span className={`num ${color} ${className}`} data-testid={testId}>
      <PointsFigure cents={cents} signed={signed} />
    </span>
  );
}

/** A points figure with its unit set quieter; reads as "+1,800 pts". */
export function PointsFigure({
  cents,
  signed = false,
}: {
  cents: number;
  signed?: boolean;
}) {
  return (
    <>
      {signed && cents > 0 ? '+' : ''}
      {formatPointsValue(cents)}
      <span className="pts-unit"> pts</span>
    </>
  );
}
