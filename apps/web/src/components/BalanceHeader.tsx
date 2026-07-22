import { formatCurrency } from '../lib/format';
import { useCountUp } from '../hooks/useCountUp';
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
  const shown = useCountUp(available);

  return (
    <div data-testid="balance-header">
      <div className="label-mono">Balance</div>
      <div className="text-[2.75rem] font-bold leading-none tracking-tight tabular-nums">
        {formatCurrency(shown)}
      </div>
      {inPlay > 0 && (
        <div className="text-sm text-text-secondary">
          {formatCurrency(inPlay)} in play
        </div>
      )}
    </div>
  );
}
