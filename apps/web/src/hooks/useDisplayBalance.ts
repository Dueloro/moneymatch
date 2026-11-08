import { useSettlement } from './useSettlement';
import { surfaceOf } from './useSettlementCelebration';
import { useWallet } from './useWallet';

export function useDisplayBalance(): number | undefined {
  const { data: wallet } = useWallet();
  const live = wallet?.available_cents;
  const { current } = useSettlement();

  const celebrating = current != null && surfaceOf(current) === 'overlay';
  if (!celebrating || live == null) return live;
  return live - current.netCents;
}
