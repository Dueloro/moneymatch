import { useEffect, useRef, useState } from 'react';

import { useCountUp } from '../../hooks/useCountUp';
import { formatCurrency } from '../../lib/format';

/**
 * A balance that shows you what just happened to it.
 *
 * Settlement is the moment the product does its job, and it used to arrive as
 * a number that was simply different from the number before — you had to
 * remember the old one to know whether you had won. The figure now counts to
 * its new value, tinted by direction, and the change itself floats off above
 * it.
 *
 * Deliberately brief. This sits in the rail and the nav on every screen, so an
 * animation that lingers becomes something to wait out rather than something
 * to notice.
 */

/** How long the delta stays on screen. */
const DELTA_MS = 2200;

/** How long the figure stays tinted. Shorter — the colour is the loud part. */
const TINT_MS = 1400;

export function AnimatedBalance({
  cents,
  className = '',
  testId,
}: {
  /**
   * The available balance in cents, or `undefined` until the wallet has loaded.
   * Undefined renders a quiet placeholder and is *not* treated as a value — so a
   * normal login or refresh (0-while-loading → real balance) no longer flashes
   * through $0 or fires a phantom "+$X". The animating inner only mounts once a
   * real number exists, so it seeds on the true balance and stays silent until
   * an *actual* change (a settlement, a deposit) moves it.
   */
  cents: number | undefined;
  className?: string;
  testId?: string;
}) {
  if (cents == null) {
    return (
      <span
        className={`tabular-nums text-text-tertiary ${className}`}
        data-testid={testId}
      >
        —
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
  // First render is not a change. Without this, opening any page announces
  // your whole balance as a win.
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
  // The balance is green at rest, so a win cannot be signalled by turning it
  // green. A loss goes red; a win brightens instead.
  const tint = tinted ? (up ? 'text-live' : 'text-red') : '';

  return (
    <span className={`relative inline-block ${className}`} data-testid={testId}>
      <span
        className={`tabular-nums transition-colors duration-300 ${tint}`}
        data-direction={delta === null ? 'none' : up ? 'up' : 'down'}
      >
        {formatCurrency(shown)}
      </span>

      {delta !== null && (
        <span
          // aria-hidden: the figure beside it is already announced, and screen
          // readers reading a number that is mid-flight is noise.
          aria-hidden
          data-testid={testId ? `${testId}-delta` : undefined}
          className={`animate-money-delta pointer-events-none absolute -top-4 left-1/2 whitespace-nowrap text-xs font-semibold ${
            up ? 'text-live' : 'text-red'
          }`}
        >
          {up ? '+' : '−'}
          {formatCurrency(Math.abs(delta))}
        </span>
      )}
    </span>
  );
}
