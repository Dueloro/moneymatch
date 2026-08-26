import type { CSSProperties } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { useCountUp } from '../hooks/useCountUp';
import type { SettlementOutcome } from '../hooks/useSettlementCelebration';
import { useSettlementCelebration } from '../hooks/useSettlementCelebration';
import { formatCurrency } from '../lib/format';

/**
 * The result of a wager, taking the screen for a moment.
 *
 * Settlement is the moment the product does its job. It used to happen
 * silently — a row in Activity changed state, usually while you were looking at
 * something else — so the one event worth witnessing was the one you missed.
 *
 * Two deliberately different sequences. A win **erupts**: a flash, a burst of
 * coins and confetti, a beam sweeping across. A loss **collapses**: the wager
 * token shakes, shatters, and drifts away as smoke. They should be
 * unmistakable from across a room, and neither should feel like the other with
 * a different colour.
 *
 * The whole thing is ~1.9s including the exit. It fires on any screen, at any
 * time, so it has to be over before it becomes something to wait out.
 *
 * Everything animates `transform` and `opacity` only — the two properties the
 * compositor owns. That is what keeps it smooth: a settlement invalidates half
 * the query cache, so React is re-rendering the page underneath at exactly the
 * moment this plays.
 */

/** Total sequence length, matching the CSS timelines. */
const HOLD_MS = 1_900;

/**
 * Only a win and a loss are celebrated for now.
 *
 * A push and a refund still classify correctly in the hook — a refund is *not*
 * a loss and must never be shown as one — they simply have no sequence yet.
 * Re-enabling one is adding it to this set.
 */
const CELEBRATED: ReadonlySet<SettlementOutcome> = new Set<SettlementOutcome>([
  'win',
  'loss',
]);

/**
 * Particle counts.
 *
 * The brief asked for "thousands of coins". Thousands of DOM nodes would stop
 * being an animation and start being a stutter, and the illusion does not need
 * them: a wide spread of vectors and staggered delays reads as an explosion at
 * around forty. Every extra element is another layer for the compositor.
 */
const BURST_COUNT = 38;
const SHARD_COUNT = 22;
const SMOKE_COUNT = 7;
const SPARK_COUNT = 6;

type Kind = 'coin' | 'bill' | 'confetti';

interface Particle {
  kind: Kind;
  style: CSSProperties;
  size: number;
  colour: string;
}

/** Stable pseudo-random in [0,1) — same burst every time, no layout thrash. */
function rnd(i: number, salt: number): number {
  return Math.abs(Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453) % 1;
}

function makeBurst(): Particle[] {
  // Gold leads, because a win should read as *money*; the brand lime and the
  // live cyan keep it ours rather than generic casino.
  const confettiColours = [
    'var(--green)',
    'var(--live)',
    'var(--action)',
    'var(--warn)',
  ];

  return Array.from({ length: BURST_COUNT }, (_, i) => {
    const angle = (i / BURST_COUNT) * Math.PI * 2 + rnd(i, 1) * 0.7;
    const dist = 120 + rnd(i, 2) * 260;
    const kind: Kind = i % 3 === 0 ? 'coin' : i % 3 === 1 ? 'bill' : 'confetti';
    const size = kind === 'coin' ? 14 + rnd(i, 3) * 8 : kind === 'bill' ? 16 : 7;

    return {
      kind,
      size,
      colour:
        kind === 'confetti'
          ? confettiColours[i % confettiColours.length]
          : 'transparent',
      style: {
        '--tx': `${Math.cos(angle) * dist}px`,
        '--ty': `${Math.sin(angle) * dist - 40}px`,
        '--rot': `${(rnd(i, 4) - 0.5) * 720}deg`,
        '--fall': `${180 + rnd(i, 5) * 260}px`,
        '--dur': `${1.35 + rnd(i, 6) * 0.5}s`,
        '--delay': `${rnd(i, 7) * 0.12}s`,
      } as CSSProperties,
    };
  });
}

function makeShards(): CSSProperties[] {
  return Array.from({ length: SHARD_COUNT }, (_, i) => {
    const angle = (i / SHARD_COUNT) * Math.PI * 2 + rnd(i, 11) * 0.6;
    const dist = 40 + rnd(i, 12) * 120;
    return {
      '--tx': `${Math.cos(angle) * dist}px`,
      '--ty': `${Math.sin(angle) * dist * 0.6}px`,
      '--rot': `${(rnd(i, 13) - 0.5) * 540}deg`,
      '--fall': `${120 + rnd(i, 14) * 180}px`,
      '--delay': `${rnd(i, 15) * 0.1}s`,
      width: 4 + Math.round(rnd(i, 16) * 7),
      height: 3 + Math.round(rnd(i, 17) * 6),
      background: i % 3 === 0 ? 'var(--red)' : i % 3 === 1 ? '#6b4a45' : '#3a3f47',
      borderRadius: '1px',
    } as CSSProperties;
  });
}

export function SettlementCelebration() {
  const { current, dismiss } = useSettlementCelebration();
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const [target, setTarget] = useState(0);
  const amount = useCountUp(target, 850);

  const show = current && CELEBRATED.has(current.outcome) ? current : null;
  const burst = useMemo(makeBurst, []);
  const shards = useMemo(makeShards, []);

  useEffect(() => {
    if (!current) return;
    // Outcomes with no sequence are still consumed, so the queue drains and
    // they are never re-announced later.
    timer.current = setTimeout(dismiss, show ? HOLD_MS : 0);
    return () => clearTimeout(timer.current);
  }, [current, show, dismiss]);

  useEffect(() => {
    setTarget(show ? Math.abs(show.netCents) : 0);
  }, [show]);

  useEffect(() => {
    if (!show) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dismiss();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [show, dismiss]);

  if (!show) return null;

  const win = show.outcome === 'win';
  const headline = win ? 'YOU WIN!' : 'WAGER LOST';
  const announced = win
    ? `You won ${formatCurrency(show.netCents)} on ${show.title}`
    : `You lost ${formatCurrency(Math.abs(show.netCents))} on ${show.title}`;

  return (
    <div
      role="status"
      aria-live="polite"
      onClick={dismiss}
      className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden"
      data-testid="settlement-celebration"
      data-outcome={show.outcome}
    >
      {/* Veil. Blue-violet lifts a win off the dark UI; desaturated red drops a
       * loss into it. Static gradients, so only opacity animates. */}
      <div
        aria-hidden="true"
        className="mm-veil absolute inset-0"
        style={{
          background: win
            ? 'radial-gradient(circle at 50% 45%, rgb(88 70 190 / 0.42), rgb(11 12 15 / 0.86) 62%)'
            : 'radial-gradient(circle at 50% 45%, rgb(120 60 55 / 0.34), rgb(11 12 15 / 0.9) 62%)',
        }}
      />

      <span className="sr-only">{announced}</span>

      <div className="relative flex flex-col items-center" aria-hidden="true">
        {/* ── The burst, centred on the text ── */}
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-0 w-0">
          <div
            className="mm-flash absolute -left-24 -top-24 h-48 w-48 rounded-full"
            style={{
              background: win
                ? 'radial-gradient(circle, rgb(255 236 170 / 0.95), rgb(245 185 60 / 0.5) 42%, transparent 70%)'
                : 'radial-gradient(circle, rgb(255 140 120 / 0.8), rgb(255 95 72 / 0.35) 42%, transparent 70%)',
            }}
          />
          <div
            className="mm-ring absolute -left-16 -top-16 h-32 w-32 rounded-full border-2"
            style={{
              borderColor: win ? 'rgb(245 185 60 / 0.7)' : 'rgb(255 95 72 / 0.6)',
            }}
          />

          {win
            ? burst.map((p, i) => (
                <span key={i} className="mm-burst absolute" style={p.style}>
                  {p.kind === 'coin' ? (
                    <span
                      className="mm-spin block rounded-full"
                      style={{
                        width: p.size,
                        height: p.size,
                        background:
                          'linear-gradient(145deg, #ffe89a, #f5b93c 45%, #c98b18)',
                        boxShadow: 'inset 0 0 0 1.5px rgb(255 255 255 / 0.45)',
                        ...(p.style as CSSProperties),
                      }}
                    />
                  ) : p.kind === 'bill' ? (
                    <span
                      className="block"
                      style={{
                        width: p.size + 8,
                        height: p.size * 0.6,
                        borderRadius: 2,
                        background:
                          'linear-gradient(135deg, #dff5a8, #a9d94b 60%, #7fae2f)',
                        boxShadow: 'inset 0 0 0 1px rgb(255 255 255 / 0.35)',
                      }}
                    />
                  ) : (
                    <span
                      className="block"
                      style={{
                        width: p.size,
                        height: p.size,
                        background: p.colour,
                        borderRadius: i % 2 ? '999px' : '1px',
                      }}
                    />
                  )}
                </span>
              ))
            : null}

          {/* ── The loss: token, shatter, smoke ── */}
          {!win ? (
            <>
              <span
                className="mm-shake absolute -left-7 -top-7 flex h-14 w-14 items-center justify-center rounded-full"
                style={{
                  background: 'linear-gradient(145deg, #2c313a, #191d24)',
                  boxShadow: 'inset 0 0 0 2px rgb(255 95 72 / 0.55)',
                }}
              >
                <span className="text-[10px] font-bold tracking-wider text-red">M</span>
              </span>
              {shards.map((st, i) => (
                <span key={i} className="mm-shard absolute block" style={st} />
              ))}
              {Array.from({ length: SMOKE_COUNT }, (_, i) => (
                <span
                  key={`s${i}`}
                  className="mm-smoke absolute block rounded-full"
                  style={
                    {
                      left: -30 + rnd(i, 21) * 60,
                      top: -20 + rnd(i, 22) * 30,
                      width: 34 + rnd(i, 23) * 38,
                      height: 34 + rnd(i, 23) * 38,
                      background:
                        'radial-gradient(circle, rgb(150 110 105 / 0.5), transparent 68%)',
                      '--tx': `${(rnd(i, 24) - 0.5) * 70}px`,
                      '--delay': `${rnd(i, 25) * 0.2}s`,
                    } as CSSProperties
                  }
                />
              ))}
            </>
          ) : null}
        </div>

        {/* ── Headline and amount ── */}
        <h2
          className={[
            win ? 'mm-title' : 'mm-title-down',
            'relative select-none text-center font-black tracking-tight',
          ].join(' ')}
          style={
            // Sized inline, not with a utility: the Tailwind fontSize scale here
            // is *overridden* rather than extended and stops at `3xl`, so
            // `text-5xl` silently resolves to nothing. Display type for a
            // full-screen moment does not belong on the body scale anyway.
            win
              ? {
                  fontSize: 'clamp(2.75rem, 9vw, 4.5rem)',
                  lineHeight: 1.05,
                  backgroundImage:
                    'linear-gradient(180deg, #fffdf3 8%, #ffe89a 42%, #f5b93c 78%)',
                  WebkitBackgroundClip: 'text',
                  backgroundClip: 'text',
                  color: 'transparent',
                  textShadow: '0 0 26px rgb(245 185 60 / 0.35)',
                }
              : {
                  fontSize: 'clamp(2.5rem, 8vw, 4rem)',
                  lineHeight: 1.05,
                  color: 'var(--red)',
                  textShadow: '0 2px 18px rgb(255 95 72 / 0.3)',
                }
          }
        >
          {headline}
        </h2>

        <div className="mm-amount relative mt-3 flex items-center gap-2">
          {win
            ? Array.from({ length: SPARK_COUNT }, (_, i) => (
                <span
                  key={i}
                  className="mm-spark absolute block rounded-full"
                  style={
                    {
                      left: `${8 + rnd(i, 31) * 84}%`,
                      top: `${-40 + rnd(i, 32) * 150}%`,
                      width: 4 + rnd(i, 33) * 3,
                      height: 4 + rnd(i, 33) * 3,
                      background: '#fff6d0',
                      boxShadow: '0 0 8px 2px rgb(255 232 154 / 0.8)',
                      '--delay': `${rnd(i, 34) * 0.3}s`,
                    } as CSSProperties
                  }
                />
              ))
            : null}
          <span
            className={[
              'font-bold tabular-nums',
              win ? 'text-warn' : 'text-text-secondary',
            ].join(' ')}
            style={{ fontSize: 'clamp(1.75rem, 5vw, 2.75rem)', lineHeight: 1.1 }}
          >
            {win ? '+' : '−'}
            {formatCurrency(amount)}
          </span>
        </div>

        <p className="mm-amount mt-2 max-w-xs truncate text-center text-xs text-text-tertiary">
          {show.title}
        </p>
      </div>

      {/* A single beam across a win; a hairline crack across a loss. */}
      {win ? (
        <span
          aria-hidden="true"
          className="mm-beam pointer-events-none absolute inset-y-0 -left-1/4 w-1/4"
          style={{
            background:
              'linear-gradient(90deg, transparent, rgb(255 240 190 / 0.16), transparent)',
          }}
        />
      ) : (
        <span
          aria-hidden="true"
          className="mm-crack pointer-events-none absolute left-0 top-1/2 h-px w-full"
          style={{
            background:
              'linear-gradient(90deg, transparent, rgb(255 95 72 / 0.55) 35%, rgb(255 95 72 / 0.2) 55%, transparent)',
          }}
        />
      )}
    </div>
  );
}
