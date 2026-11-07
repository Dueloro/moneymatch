import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useWaitedSeconds } from './useWaitedSeconds';

describe('useWaitedSeconds', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('ticks locally between polls and re-seeds only on real drift', () => {
    const { result, rerender } = renderHook(({ s }) => useWaitedSeconds(s), {
      initialProps: { s: 10 as number | null },
    });
    expect(result.current).toBe(10);
    act(() => void vi.advanceTimersByTime(3000));
    expect(result.current).toBe(13);
    rerender({ s: 12 });
    expect(result.current).toBe(13);
    rerender({ s: 40 });
    expect(result.current).toBe(40);
  });
});
