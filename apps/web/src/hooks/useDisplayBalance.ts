import { useSettlement } from './useSettlement';
import { useWallet } from './useWallet';

/**
 * The balance to show in the nav / rail / header.
 *
 * Normally this is just the live wallet balance. While a *settlement overlay* is
 * on screen, though, it holds the balance at its pre-settlement value so the
 * tick to the new number lands right after the overlay closes (item 4) rather
 * than running invisibly behind the full-screen celebration.
 *
 * The pre-settlement value is reconstructed as `live − balanceDeltaCents`: by
 * the time the overlay is up the wallet has usually already taken the result,
 * so backing out what settlement added yields the amount from *before* it. For
 * a tournament that is the prize, not the net: the entry left the balance when
 * you joined (backing out the net showed a wrong red "−$200" on a $225 win).
 * When the overlay dismisses, the hook returns `live` again and `AnimatedBalance`
 * animates the difference — the same primitive item 3 uses, fired at the right
 * moment. Worst case (a timing skew) it reveals with no tick, never a wrong one.
 */
export function useDisplayBalance(): number | undefined {
  const { data: wallet } = useWallet();
  const live = wallet?.available_cents;
  const { current } = useSettlement();

  const celebrating =
    current != null && (current.outcome === 'win' || current.outcome === 'loss');
  if (!celebrating || live == null) return live;
  return live - current.balanceDeltaCents;
}
