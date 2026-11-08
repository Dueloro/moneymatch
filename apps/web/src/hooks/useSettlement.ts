import { createContext, useContext, useEffect } from 'react';

import type { Settlement } from './useSettlementCelebration';

export interface SettlementValue {
  current: Settlement | null;
  dismiss: () => void;
  /** Show this contest's result in place: no toast or overlay for it. */
  claim: (id: string) => () => void;
}

export const SettlementContext = createContext<SettlementValue>({
  current: null,
  dismiss: () => {},
  claim: () => () => {},
});

export function useSettlement(): SettlementValue {
  return useContext(SettlementContext);
}

/** The match stage owns its own result moment. */
export function useClaimSettlement(id: string | undefined): void {
  const { claim } = useContext(SettlementContext);
  useEffect(() => (id ? claim(id) : undefined), [id, claim]);
}
