import { useCallback, useState } from 'react';
import type { SettlementResult } from '../types';

/** Owns the single active settlement popup (win/lose/refund moment). */
export function useSettlement() {
  const [result, setResult] = useState<SettlementResult | null>(null);
  const show = useCallback((r: SettlementResult) => setResult(r), []);
  const dismiss = useCallback(() => setResult(null), []);
  return { result, show, dismiss };
}
