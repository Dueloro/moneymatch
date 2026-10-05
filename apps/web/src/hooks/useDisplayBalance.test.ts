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
    game: 'cs2.steam',
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
    // Wallet has already taken the win (100_000 → 109_000); the display backs
    // the net out so the number the user sees behind the veil is the old one.
    wallet.data = { available_cents: 109_000 };
    settlement.current = settle({
      outcome: 'win',
      netCents: 9_000,
      balanceDeltaCents: 9_000,
    });
    expect(renderHook(() => useDisplayBalance()).result.current).toBe(100_000);
  });

  it('holds at the pre-loss balance while a loss overlay is up', () => {
    wallet.data = { available_cents: 97_500 };
    settlement.current = settle({
      outcome: 'loss',
      netCents: -2_500,
      balanceDeltaCents: -2_500,
    });
    expect(renderHook(() => useDisplayBalance()).result.current).toBe(100_000);
  });

  it('backs out the prize, not the net, for a tournament win', () => {
    // $25 entry left the balance at join (962 available); a $225 prize lands:
    // 1187. Behind the overlay the display must read 962, then tick +$225.
    wallet.data = { available_cents: 118_700 };
    settlement.current = settle({
      outcome: 'win',
      type: 'tournament',
      netCents: 20_000,
      amountCents: 22_500,
      balanceDeltaCents: 22_500,
    });
    expect(renderHook(() => useDisplayBalance()).result.current).toBe(96_200);
  });

  it('reveals the new balance once the overlay is dismissed', () => {
    // After dismiss `current` clears; the live (post-win) balance flows through
    // and AnimatedBalance animates the difference — the tick, now visible.
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
