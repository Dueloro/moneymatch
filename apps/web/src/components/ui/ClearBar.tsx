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
  lowerIsBetter = false,
  size = 'md',
}: {
  current: number | null | undefined;
  target: number;
  label?: string;
  cleared?: boolean;
  lowerIsBetter?: boolean;
  size?: 'sm' | 'md';
}) {
  const span = Math.max(target, current ?? 0) || 1;
  const scale = (v: number) => Math.max(0, Math.min(100, (v / (span * 1.28)) * 100));
  const targetPct = scale(target);
  const currentPct = current == null ? 0 : scale(current);
  const short =
    current != null && (lowerIsBetter ? current > target : current < target);
  const gap =
    current == null ? null : lowerIsBetter ? current - target : target - current;
  const gapLeft = lowerIsBetter ? targetPct : currentPct;
  const gapWidth = Math.abs(targetPct - currentPct);

  const trackH = size === 'sm' ? 'h-1' : 'h-1.5';
  const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2));

  return (
    <div>
      <div className={`relative ${trackH} w-full rounded-pill bg-panel-raised`}>
        <div
          className={[
            'absolute inset-y-0 left-0 rounded-pill',
            cleared ? 'bg-green' : 'bg-text-tertiary',
          ].join(' ')}
          style={{ width: `${currentPct}%` }}
        />
        {short && !cleared && (
          <div
            data-testid="clear-gap"
            className="absolute inset-y-0 rounded-pill bg-live/25"
            style={{ left: `${gapLeft}%`, width: `${gapWidth}%` }}
          />
        )}
        <div
          className="absolute -top-1 bottom-[-0.25rem] w-0.5 rounded-pill bg-text"
          style={{ left: `${targetPct}%` }}
          aria-hidden
        />
      </div>

      <div className="mt-2 flex items-baseline justify-between gap-3 text-xs tabular-nums">
        <span className="text-text-secondary">
          {label ?? 'your bar'}{' '}
          <span className="text-text">{current == null ? '-' : fmt(current)}</span>
        </span>
        {gap != null && gap > 0 && (
          <span className="text-text-tertiary">
            need {lowerIsBetter ? '−' : '+'}
            {fmt(gap)}
          </span>
        )}
        {gap != null && gap < 0 && lowerIsBetter && (
          <span className="text-green">{fmt(-gap)} under</span>
        )}
        {gap != null && (gap === 0 || (gap < 0 && !lowerIsBetter)) && (
          <span className="text-green">clear</span>
        )}
      </div>
    </div>
  );
}
