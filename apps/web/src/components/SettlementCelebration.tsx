import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { useCountUp } from '../hooks/useCountUp';
import { useSettlement } from '../hooks/useSettlement';
import { surfaceOf } from '../hooks/useSettlementCelebration';
import { formatPoints } from '../lib/format';
import { settlementToast } from '../lib/settlementToast';
import { toast } from '../lib/toast';
import { AmountText } from './ui/AmountText';
import { WinMark } from './play/ResultMarks';

const HOLD_MS = 3_000;

/**
 * The settlement moment away from the match stage. A pool or tournament win gets a
 * light result card over the page; every other result is a toast that links to it.
 * Head-to-head results the stage is showing are claimed there and skip this.
 */
export function SettlementCelebration() {
  const { current, dismiss } = useSettlement();
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const toasted = useRef<string | null>(null);

  const show = current && surfaceOf(current) === 'overlay' ? current : null;

  const [target, setTarget] = useState(0);
  const amount = useCountUp(target, 850);
  useEffect(() => setTarget(show ? show.amountCents : 0), [show]);

  useEffect(() => {
    if (!current || show) return;
    if (toasted.current !== current.id) {
      toasted.current = current.id;
      const t = settlementToast(current);
      toast[t.kind](t.text, { label: 'View', to: t.to });
    }
    dismiss();
  }, [current, show, dismiss]);

  useEffect(() => {
    if (!show) return;
    timer.current = setTimeout(dismiss, HOLD_MS);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dismiss();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      clearTimeout(timer.current);
      window.removeEventListener('keydown', onKey);
    };
  }, [show, dismiss]);

  if (!show) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      onClick={dismiss}
      className="fixed inset-0 z-50 flex items-end justify-center bg-bg/70 p-4 md:items-center"
      data-testid="settlement-celebration"
      data-outcome={show.outcome}
    >
      <span className="sr-only">
        You won {formatPoints(show.amountCents, { long: true })} on {show.title}
      </span>
      <div className="mm-result-glow animate-rise relative w-full max-w-sm overflow-hidden rounded-card border border-line-strong bg-overlay px-6 py-6 text-center shadow-overlay">
        <div aria-hidden="true">
          <WinMark className="mx-auto mb-4" />
          <p className="text-2xl font-semibold text-text">You won</p>
          <p data-testid="settlement-amount" className="mt-2 text-3xl font-semibold">
            <AmountText cents={amount} signed={false} money />
          </p>
          <p className="mt-2 truncate text-sm text-text-secondary">{show.title}</p>
        </div>
        <Link
          to="/activity"
          onClick={(e) => e.stopPropagation()}
          className="mt-4 inline-block text-xs text-text-tertiary underline-offset-2 hover:text-text hover:underline"
        >
          See it in Activity
        </Link>
      </div>
    </div>
  );
}
