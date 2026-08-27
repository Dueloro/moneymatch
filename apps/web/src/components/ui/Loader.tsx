import { useEffect, useState } from 'react';

/**
 * The app's one loading indicator: a pixel grid that shimmers in a diagonal
 * wave with an elapsed-time readout, so a wait reads as "working" rather than
 * "stuck". Reimplemented from the beautifui.dev "Loading State" in our tokens —
 * no canvas, no deps. Honours prefers-reduced-motion (static grid, no timer).
 *
 * Use it for full-screen waits (route/auth gates). For content that loads in
 * place — lists, rows — reach for Skeleton instead.
 */

const GRID = 5; // 5×5 pixels
const CELLS = Array.from({ length: GRID * GRID }, (_, i) => i);
const WAVE_SECONDS = 1.1;

export function Loader({
  label = 'Loading',
  fullScreen = true,
}: {
  label?: string;
  fullScreen?: boolean;
}) {
  const reduced = usePrefersReducedMotion();
  const elapsed = useElapsed(!reduced);

  const content = (
    <div
      role="status"
      aria-live="polite"
      aria-label={label}
      className="flex flex-col items-center gap-4"
    >
      <div className="grid grid-cols-5 gap-1" aria-hidden>
        {CELLS.map((i) => {
          // Diagonal distance drives the delay, so the shimmer sweeps corner to
          // corner instead of every cell pulsing in unison.
          const row = Math.floor(i / GRID);
          const col = i % GRID;
          const delay = ((row + col) / (2 * (GRID - 1))) * WAVE_SECONDS;
          return (
            <span
              key={i}
              className="h-2.5 w-2.5 rounded-[3px] bg-text-secondary opacity-30 animate-pulse motion-reduce:animate-none motion-reduce:opacity-40"
              style={{
                animationDelay: `${delay.toFixed(2)}s`,
                animationDuration: `${WAVE_SECONDS}s`,
              }}
            />
          );
        })}
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className="text-text-secondary">{label}</span>
        {!reduced && (
          <span className="font-mono tabular-nums text-text-tertiary">
            {elapsed.toFixed(1)}s
          </span>
        )}
      </div>
    </div>
  );

  if (!fullScreen) return content;
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg">{content}</div>
  );
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== 'undefined' &&
      !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mq) return;
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);
  return reduced;
}

/** Seconds since mount, updated 10×/s. Paused entirely when `run` is false. */
function useElapsed(run: boolean) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!run) return;
    const start = performance.now();
    const id = setInterval(() => setSeconds((performance.now() - start) / 1000), 100);
    return () => clearInterval(id);
  }, [run]);
  return seconds;
}
