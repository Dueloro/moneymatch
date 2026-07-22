import { useEffect, useRef, useState } from 'react';

/**
 * Animate an integer toward `target` whenever it changes (e.g. a balance after a
 * win or deposit). No animation on first mount, and it respects reduced-motion.
 */
export function useCountUp(target: number, durationMs = 600): number {
  const [value, setValue] = useState(target);
  const prev = useRef(target);

  useEffect(() => {
    const from = prev.current;
    const to = target;
    prev.current = to;
    if (from === to) return;

    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      setValue(to);
      return;
    }

    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(from + (to - from) * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs]);

  return value;
}
