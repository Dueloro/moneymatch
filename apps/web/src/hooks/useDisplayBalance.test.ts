import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Settlement } from './useSettlementCelebration';
import { useDisplayBalance } from './useDisplayBalance';

const wallet = vi.hoisted(() => ({
  data: undefined as { available_cents: number } | undefined,
}));
const settlement = vi.hoisted(() => ({ current: null as Settlement | null }));

vi.mock('./useWallet', () => ({ useWallet: () => wallet }));
vi.mock('./useSettlement', () => ({
  useSettlement: () => ({ current: settlement.current, dismiss: () => {} }),
}));

function settle(over: Partial<Settlement>): Settlement {
  return {
    id: 's1',
    outcome: 'win',
    netCents: 9_000,
    amountCents: 9_000,
    balanceDeltaCents: 9_000,
    title: 'Kills · Easy pool',
    game: 'chess.lichess',
    type: 'pool',
    ...over,
  };
}

describe('useDisplayBalance — holds the tick until the overlay closes', () => {
  beforeEach(() => {
    wallet.data = { available_cents: 100_000 };
    settlement.current = null;
  });

  it('passes the live balance through when nothing is settling', () => {
    expect(renderHook(() => useDisplayBalance()).result.current).toBe(100_000);
  });

  it('stays undefined while the wallet is still loading', () => {
    wallet.data = undefined;
    expect(renderHook(() => useDisplayBalance()).result.current).toBeUndefined();
  });

  it('holds at the pre-win balance while a win overlay is up', () => {
    wallet.data = { available_cents: 109_000 };
    settlement.current = settle({ outcome: 'win', netCents: 9_000 });
    expect(renderHook(() => useDisplayBalance()).result.current).toBe(100_000);
  });

  it('backs a tournament win out by its prize rather than its net profit', () => {
    wallet.data = { available_cents: 102_250 };
    settlement.current = settle({
      type: 'tournament',
      netCents: 250,
      amountCents: 2_250,
      balanceDeltaCents: 2_250,
    });
    expect(renderHook(() => useDisplayBalance()).result.current).toBe(100_000);
  });

  it('does not hold for a loss (a toast, no overlay)', () => {
    wallet.data = { available_cents: 97_500 };
    settlement.current = settle({ outcome: 'loss', netCents: -2_500 });
    expect(renderHook(() => useDisplayBalance()).result.current).toBe(97_500);
  });

  it('does not hold for a head-to-head win (the match stage shows it)', () => {
    wallet.data = { available_cents: 109_000 };
    settlement.current = settle({ type: 'match', netCents: 9_000 });
    expect(renderHook(() => useDisplayBalance()).result.current).toBe(109_000);
  });

  it('reveals the new balance once the overlay is dismissed', () => {
    wallet.data = { available_cents: 109_000 };
    settlement.current = null;
    expect(renderHook(() => useDisplayBalance()).result.current).toBe(109_000);
  });

  it('does not hold for a push or refund (no overlay for those)', () => {
    wallet.data = { available_cents: 100_000 };
    settlement.current = settle({ outcome: 'push', netCents: 0 });
    expect(renderHook(() => useDisplayBalance()).result.current).toBe(100_000);
  });
});
