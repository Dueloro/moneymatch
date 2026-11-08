import { AnimatedBalance } from './ui/AnimatedBalance';
import { formatPoints } from '../lib/format';
import { useDisplayBalance } from '../hooks/useDisplayBalance';
import { useWallet } from '../hooks/useWallet';

export function BalanceHeader() {
  const { data: wallet } = useWallet();
  const available = useDisplayBalance();
  const inPlay = wallet?.escrow_cents ?? 0;

  return (
    <div
      data-testid="balance-header"
      className="ml-auto shrink-0 whitespace-nowrap text-right text-sm leading-tight"
    >
      <span className="label-money mr-2 align-middle">Balance</span>
      <span className="align-middle font-semibold">
        <AnimatedBalance cents={available} testId="header-balance" />
      </span>
      {inPlay > 0 && (
        <span className="ml-2 align-middle text-xs text-text-secondary">
          · {formatPoints(inPlay)} in play
        </span>
      )}
    </div>
  );
}
