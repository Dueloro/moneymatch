import { createContext, useContext } from 'react';

import type { Settlement } from './useSettlementCelebration';

export interface SettlementValue {
  current: Settlement | null;
  dismiss: () => void;
}

export const SettlementContext = createContext<SettlementValue>({
  current: null,
  dismiss: () => {},
});

export function useSettlement(): SettlementValue {
  return useContext(SettlementContext);
}
