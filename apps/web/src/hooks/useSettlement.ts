import { createContext, useContext } from 'react';

import type { Settlement } from './useSettlementCelebration';

/**
 * The shared settlement stream, split from its provider so the provider file can
 * export only a component (react-refresh), mirroring `auth/useAuth` +
 * `auth/AuthProvider`. The default is a no-op so a component used without the
 * provider (a lone balance widget in a unit test) sees "no settlement".
 */
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
