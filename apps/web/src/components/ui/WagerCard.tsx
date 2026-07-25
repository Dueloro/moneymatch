import { formatCurrency } from '../../lib/format';
import { PillButton } from './PillButton';

/**
 * A single joinable wager (pool / tournament / head-to-head) as a self-contained
 * rounded card: game + difficulty tag, what you're wagering on, a pre-set entry
 * fee, how full it is, an estimated payout, and a Join button. Reused across all
 * three modes so they read consistently.
 */
export function WagerCard({
  accent,
  gameName,
  tag,
  title,
  subtitle,
  entryCents,
  capacity,
  filled,
  oneVsOne = false,
  footnote,
  buttonLabel,
  onJoin,
  disabled = false,
  joining = false,
}: {
  accent: string;
  gameName: string;
  tag?: string;
  title: string;
  subtitle: string;
  entryCents: number;
  capacity: number;
  filled: number;
  oneVsOne?: boolean;
  footnote?: string;
  buttonLabel: string;
  onJoin: () => void;
  disabled?: boolean;
  joining?: boolean;
}) {
  const pct = capacity > 0 ? Math.min(100, Math.round((filled / capacity) * 100)) : 0;

  return (
    <div className="flex flex-col rounded-2xl border border-hairline bg-panel p-4 transition hover:border-text-secondary/50">
      <div className="flex items-start justify-between gap-2">
        <span
          className="rounded-pill px-2 py-0.5 text-[11px] font-semibold"
          style={{ color: accent, backgroundColor: `${accent}22` }}
        >
          {gameName}
        </span>
        {tag && (
          <span className="rounded-pill bg-panel-raised px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-secondary">
            {tag}
          </span>
        )}
      </div>

      <h3 className="mt-3 text-lg font-bold leading-tight text-text">{title}</h3>
      <p className="mt-1 text-sm text-text-secondary">{subtitle}</p>

      <div className="mt-4 flex items-end justify-between">
        <div>
          <div className="label-mono">Entry</div>
          <div className="text-xl font-bold tabular-nums">
            {formatCurrency(entryCents)}
          </div>
        </div>
        <div className="text-right">
          {oneVsOne ? (
            <div className="text-sm font-semibold text-text">1v1</div>
          ) : (
            <div className="text-sm font-semibold text-text tabular-nums">
              {filled} of {capacity} joined
            </div>
          )}
          {footnote && <div className="mt-0.5 text-xs text-green">{footnote}</div>}
        </div>
      </div>

      {!oneVsOne && (
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-panel-raised">
          <div
            className="h-full rounded-full"
            style={{ width: `${pct}%`, backgroundColor: accent }}
          />
        </div>
      )}

      <div className="mt-4">
        <PillButton fullWidth disabled={disabled || joining} onClick={onJoin}>
          {joining ? 'Joining…' : buttonLabel}
        </PillButton>
      </div>
    </div>
  );
}
