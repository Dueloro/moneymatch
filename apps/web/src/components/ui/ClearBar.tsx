/**
 * The clear bar: this product's signature object (16-ui-revamp-plan §6).
 *
 * MoneyMatch's whole idea is "here is a number quoted from your own baseline,
 * now beat it". This renders exactly that: your average sits on a track, the
 * target sits to the right of it, and the gap you have to cover is shaded. It
 * replaces the sentence "Clears ≈ 16% of the time" with a picture, and it
 * encodes difficulty spatially, so a harder pool is visibly a longer reach.
 *
 * The same component appears on the contest card, the formed-room banner, the
 * live line in Activity, and the rail's in-play card, so it reads as the
 * product's object rather than as a chart. Nothing else in the UI is this loud.
 */
/**
 * The browse-card variant. The pools markets endpoint quotes a bar and a clear
 * rate but **not** your baseline, so a full ClearBar there would have to invent
 * the "you" end of it. This shows the real number instead: how often the server
 * expects you to clear that bar, as a meter rather than as the sentence
 * "Clears ≈ 31% of the time" repeated on every card.
 *
 * Harder bars read as visibly shorter meters, which is the difficulty signal
 * the three cards exist to communicate.
 */
export function ClearRate({ rate }: { rate: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(rate * 100)));
  return (
    <div>
      <div className="h-1.5 w-full overflow-hidden rounded-pill bg-panel-raised">
        <div
          className="h-full rounded-pill bg-text-tertiary"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-text-secondary">
        <span className="text-text">{pct}%</span> of your recent matches clear it
      </p>
    </div>
  );
}

export function ClearBar({
  current,
  target,
  label,
  cleared,
  size = 'md',
}: {
  /** Your baseline, or your live value once a contest is running. */
  current: number | null | undefined;
  /** The number you have to beat. */
  target: number;
  /** Unit caption under the left end, e.g. "your avg". */
  label?: string;
  /** Once known: true paints the covered track in money lime. */
  cleared?: boolean;
  size?: 'sm' | 'md';
}) {
  // Scale so the target sits at 78% of the track, which leaves the overshoot
  // room to read as overshoot rather than as a full bar.
  const span = Math.max(target, current ?? 0) || 1;
  const scale = (v: number) => Math.max(0, Math.min(100, (v / (span * 1.28)) * 100));
  const targetPct = scale(target);
  const currentPct = current == null ? 0 : scale(current);
  const short = current != null && current < target;
  const gap = current == null ? null : target - current;

  const trackH = size === 'sm' ? 'h-1' : 'h-1.5';
  const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2));

  return (
    <div>
      <div className={`relative ${trackH} w-full rounded-pill bg-panel-raised`}>
        {/* Covered ground: how far you already are. */}
        <div
          className={[
            'absolute inset-y-0 left-0 rounded-pill',
            cleared ? 'bg-green' : 'bg-text-tertiary',
          ].join(' ')}
          style={{ width: `${currentPct}%` }}
        />
        {/* The gap you still have to cover, hatched in the live tone. */}
        {short && !cleared && (
          <div
            className="absolute inset-y-0 rounded-pill bg-live/25"
            style={{ left: `${currentPct}%`, width: `${targetPct - currentPct}%` }}
          />
        )}
        {/* The target: a full-height tick you have to get past. */}
        <div
          className="absolute -top-1 bottom-[-0.25rem] w-0.5 rounded-pill bg-text"
          style={{ left: `${targetPct}%` }}
          aria-hidden
        />
      </div>

      <div className="mt-2 flex items-baseline justify-between gap-3 text-xs">
        <span className="text-text-secondary">
          {label ?? 'your avg'}{' '}
          <span className="text-text">{current == null ? '-' : fmt(current)}</span>
        </span>
        {gap != null && gap > 0 && (
          <span className="text-text-tertiary">need +{fmt(gap)}</span>
        )}
        {gap != null && gap <= 0 && <span className="text-green">clear</span>}
      </div>
    </div>
  );
}
