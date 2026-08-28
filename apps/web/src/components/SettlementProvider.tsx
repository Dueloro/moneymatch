import { type ReactNode } from 'react';

import { SettlementContext } from '../hooks/useSettlement';
import { useSettlementCelebration } from '../hooks/useSettlementCelebration';

/**
 * One shared settlement stream for the whole signed-in app.
 *
 * `useSettlementCelebration` has side effects (it marks contests announced in
 * localStorage and drains a queue), so it must run exactly once. The overlay
 * consumes `current`/`dismiss` to draw the result; the balance widgets consume
 * the same `current` (via `useDisplayBalance`) to hold their tick until the
 * overlay closes. Both reading one instance is what keeps them in step.
 *
 * The context + hook live in `hooks/useSettlement` so this file exports only a
 * component (react-refresh), mirroring `auth/AuthProvider` + `auth/useAuth`.
 */
export function SettlementProvider({ children }: { children: ReactNode }) {
  const value = useSettlementCelebration();
  return (
    <SettlementContext.Provider value={value}>{children}</SettlementContext.Provider>
  );
}
