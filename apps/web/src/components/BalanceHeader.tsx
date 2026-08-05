import { formatCurrency } from '../lib/format';
import { useCountUp } from '../hooks/useCountUp';
import { useWallet } from '../hooks/useWallet';

/**
 * Compact balance readout. Deliberately understated and right-aligned: a muted
 * "Balance" label with the available figure, plus an inline "$X in play" note.
 * The balance is reference information, not the product's focus, so it sits on
 * the top-right in line with the game tabs rather than headlining the screen.
 * Reads the same `useWallet` query as the Wallet screen, so both stay in sync.
 */
export function BalanceHeader() {
  const { data: wallet } = useWallet();
  const available = wallet?.available_cents ?? 0;
  const inPlay = wallet?.escrow_cents ?? 0;
  const shown = useCountUp(available);

  return (
    <div
      data-testid="balance-header"
      className="ml-auto shrink-0 whitespace-nowrap text-right text-sm leading-tight"
    >
      <span className="label-money mr-2 align-middle">Balance</span>
      <span className="align-middle font-semibold tabular-nums">
        {formatCurrency(shown)}
      </span>
      {inPlay > 0 && (
        <span className="ml-2 align-middle text-xs text-text-secondary">
          · {formatCurrency(inPlay)} in play
        </span>
      )}
    </div>
  );
}
