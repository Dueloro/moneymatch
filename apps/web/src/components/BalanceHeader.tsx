import { formatCurrency } from '../lib/format';
import { useWallet } from '../hooks/useWallet';

/**
 * Play-screen balance header (02-design §2): tiny "Balance" label, the huge
 * available figure, and a gray "$X in play" subline. Reads the same `useWallet`
 * query as the Wallet screen, so both stay in sync.
 */
export function BalanceHeader() {
  const { data: wallet } = useWallet();
  const available = wallet?.available_cents ?? 0;
  const inPlay = wallet?.escrow_cents ?? 0;

  return (
    <div data-testid="balance-header">
      <div className="text-xs text-text-secondary">Balance</div>
      <div className="text-4xl font-bold tabular-nums">{formatCurrency(available)}</div>
      {inPlay > 0 && (
        <div className="text-sm text-text-secondary">
          {formatCurrency(inPlay)} in play
        </div>
      )}
    </div>
  );
}
