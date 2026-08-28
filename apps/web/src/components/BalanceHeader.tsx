import { AnimatedBalance } from './ui/AnimatedBalance';
import { formatCurrency } from '../lib/format';
import { useDisplayBalance } from '../hooks/useDisplayBalance';
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
  // Undefined (not `?? 0`) while loading, so AnimatedBalance shows a placeholder
  // instead of flashing $0 and animating a phantom gain on every refresh. Held
  // at its pre-settlement value while a win/loss overlay is up (see the hook).
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
          · {formatCurrency(inPlay)} in play
        </span>
      )}
    </div>
  );
}
