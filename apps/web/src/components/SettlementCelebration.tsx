import { useEffect, useRef, useState } from 'react';

import { useCountUp } from '../hooks/useCountUp';
import { useSettlement } from '../hooks/useSettlement';
import type { SettlementOutcome } from '../hooks/useSettlementCelebration';
import { formatCurrency } from '../lib/format';

/**
 * The result of a wager, taking the screen for a moment.
 *
 * Settlement is the moment the product does its job. It used to happen silently
 * — a row in Activity changed state, usually while you were looking at something
 * else — so the one event worth witnessing was the one you missed.
 *
 * The treatment is Money Match's, not a casino's: the app is quiet and dark and
 * lets exactly one thing be loud, and lime *is* money. So a **win** is stated
 * plainly and in lime — a check, "You won", the amount counting up — over a
 * faint lime wash. A **loss** is quieter still: muted, no colour, no amount, a
 * flat line rather than a shatter. The balance itself does the rest, ticking to
 * its new value once this closes (see `useDisplayBalance`).
 *
 * ~1.9s, dismissable on click or Escape. It fires on any screen, so it has to be
 * over before it becomes something to wait out.
 */

/** Total time on screen before it dismisses itself. */
const HOLD_MS = 1_900;

/**
 * Only a win and a loss are shown for now. A push and a refund still classify
 * correctly in the hook — a refund is *not* a loss and must never be shown as
 * one — they simply have no sequence. Re-enabling one is adding it here.
 */
const CELEBRATED: ReadonlySet<SettlementOutcome> = new Set<SettlementOutcome>([
  'win',
  'loss',
]);

export function SettlementCelebration() {
  const { current, dismiss } = useSettlement();
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const show = current && CELEBRATED.has(current.outcome) ? current : null;
  const win = show?.outcome === 'win';

  // The amount counts up to what you won — the app's one "money moves" gesture,
  // used here and on the balance. A loss shows no amount, so it never runs.
  const [target, setTarget] = useState(0);
  const amount = useCountUp(target, 850);
  useEffect(() => setTarget(win && show ? Math.abs(show.netCents) : 0), [win, show]);

  // Consume every outcome so the queue drains, but only hold the screen for the
  // ones that have a sequence.
  useEffect(() => {
    if (!current) return;
    timer.current = setTimeout(dismiss, show ? HOLD_MS : 0);
    return () => clearTimeout(timer.current);
  }, [current, show, dismiss]);

  useEffect(() => {
    if (!show) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dismiss();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [show, dismiss]);

  // A one-frame entrance (opacity, plus a small rise/scale for a win only), via
  // transitions so the global reduced-motion clamp turns it off for free.
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    if (!show) {
      setEntered(false);
      return;
    }
    const raf = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(raf);
  }, [show]);

  if (!show) return null;

  const headline = win ? 'You won' : 'You lost…';
  // Accessibility mirrors the visible copy: the win says the amount, the loss
  // deliberately does not.
  const announced = win
    ? `You won ${formatCurrency(show.netCents)} on ${show.title}`
    : `You lost on ${show.title}`;

  return (
    <div
      role="status"
      aria-live="polite"
      onClick={dismiss}
      className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden"
      data-testid="settlement-celebration"
      data-outcome={show.outcome}
    >
      {/* Veil. A faint lime wash lifts a win off the dark UI; a loss gets a plain
       * dim, no hue. Only opacity animates. */}
      <div
        aria-hidden="true"
        className={`absolute inset-0 transition-opacity duration-500 ${
          entered ? 'opacity-100' : 'opacity-0'
        }`}
        style={{
          background: win
            ? 'radial-gradient(circle at 50% 42%, rgb(198 244 64 / 0.10), rgb(11 12 15 / 0.92) 60%)'
            : 'rgb(11 12 15 / 0.9)',
        }}
      />

      <span className="sr-only">{announced}</span>

      <div
        aria-hidden="true"
        className={[
          'relative flex flex-col items-center px-6 text-center transition-all',
          win ? 'duration-300' : 'duration-500',
          entered
            ? 'translate-y-0 scale-100 opacity-100'
            : win
              ? 'translate-y-2 scale-95 opacity-0'
              : 'opacity-0',
        ].join(' ')}
      >
        {win ? (
          <span
            className="mb-5 grid h-16 w-16 place-items-center rounded-full"
            style={{
              background: 'rgb(198 244 64 / 0.12)',
              boxShadow: 'inset 0 0 0 1.5px rgb(198 244 64 / 0.5)',
            }}
          >
            <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" aria-hidden>
              <path
                d="M5 12.5 10 17l9-10"
                stroke="var(--green)"
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        ) : (
          <span className="mb-4 grid h-12 w-12 place-items-center rounded-full border border-hairline bg-panel-raised">
            <span className="h-0.5 w-5 rounded-full bg-text-tertiary" />
          </span>
        )}

        <h2
          className={[
            'select-none font-semibold tracking-tight',
            win ? 'text-text' : 'text-text-secondary',
          ].join(' ')}
          style={{
            fontSize: win ? 'clamp(2rem, 6vw, 3rem)' : 'clamp(1.5rem, 4vw, 2rem)',
            lineHeight: 1.1,
          }}
        >
          {headline}
        </h2>

        {/* Win only: the amount, smaller than the headline, in money-lime. */}
        {win && (
          <p
            data-testid="settlement-amount"
            className="mt-3 font-semibold tabular-nums text-green"
            style={{ fontSize: 'clamp(1.25rem, 3.5vw, 1.75rem)', lineHeight: 1.1 }}
          >
            {formatCurrency(amount)}
          </p>
        )}

        <p className="mt-3 max-w-xs truncate text-sm text-text-tertiary">
          {show.title}
        </p>
      </div>
    </div>
  );
}
