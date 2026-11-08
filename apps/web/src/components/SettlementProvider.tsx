import { type ReactNode } from 'react';

import { SettlementContext } from '../hooks/useSettlement';
import { useSettlementCelebration } from '../hooks/useSettlementCelebration';

export function SettlementProvider({ children }: { children: ReactNode }) {
  const value = useSettlementCelebration();
  return (
    <SettlementContext.Provider value={value}>{children}</SettlementContext.Provider>
  );
}
