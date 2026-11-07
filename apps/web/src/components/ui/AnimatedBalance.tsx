import { useEffect, useRef, useState } from 'react';

import { useCountUp } from '../../hooks/useCountUp';
import { formatPoints, formatPointsValue } from '../../lib/format';
import { Skeleton } from './Skeleton';

const DELTA_MS = 2200;

const TINT_MS = 1400;

export function AnimatedBalance({
  cents,
  className = '',
  testId,
}: {
  /**
   * The available balance in cents, or `undefined` until the wallet has
   * loaded.
   */
  cents: number | undefined;
  className?: string;
  testId?: string;
}) {
  if (cents == null) {
    return (
      <span className={`inline-block ${className}`} data-testid={testId} aria-busy>
        <span className="sr-only">Loading balance</span>
        <Skeleton
          inline
          className="h-[0.8em] w-[7ch] rounded-[0.25em] align-[-0.05em]"
          testId={testId ? `${testId}-skeleton` : undefined}
        />
      </span>
    );
  }
  return <LoadedBalance cents={cents} className={className} testId={testId} />;
}

function LoadedBalance({
  cents,
  className = '',
  testId,
}: {
  cents: number;
  className?: string;
  testId?: string;
}) {
  const shown = useCountUp(cents);
  const [delta, setDelta] = useState<number | null>(null);
  const previous = useRef(cents);
  const seeded = useRef(false);

  useEffect(() => {
    const from = previous.current;
    previous.current = cents;
    if (!seeded.current) {
      seeded.current = true;
      return;
    }
    if (from === cents) return;

    setDelta(cents - from);
    const timer = setTimeout(() => setDelta(null), DELTA_MS);
    return () => clearTimeout(timer);
  }, [cents]);

  const [tinted, setTinted] = useState(false);
  useEffect(() => {
    if (delta === null) return;
    setTinted(true);
    const timer = setTimeout(() => setTinted(false), TINT_MS);
    return () => clearTimeout(timer);
  }, [delta]);

  const up = (delta ?? 0) > 0;
  const tint = tinted ? (up ? 'text-green' : 'text-red') : '';

  return (
    <span className={`relative inline-block ${className}`} data-testid={testId}>
      <span
        className={`num transition-colors duration-300 ${tint}`}
        data-direction={delta === null ? 'none' : up ? 'up' : 'down'}
      >
        {formatPointsValue(shown)}{' '}
        <span className="font-sans text-[max(0.45em,0.6875rem)] font-medium tracking-normal opacity-60">
          pts
        </span>
      </span>

      {delta !== null && (
        <span
          aria-hidden
          data-testid={testId ? `${testId}-delta` : undefined}
          className={`animate-money-delta num pointer-events-none absolute -top-4 left-1/2 whitespace-nowrap text-xs font-semibold ${
            up ? 'text-green' : 'text-red'
          }`}
        >
          {up ? '+' : '−'}
          {formatPoints(Math.abs(delta))}
        </span>
      )}
    </span>
  );
}
