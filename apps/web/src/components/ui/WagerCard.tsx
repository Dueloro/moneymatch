import { useState } from 'react';

import { formatCurrency } from '../../lib/format';
import { Card } from './Card';
import { ClearRate } from './ClearBar';
import { PillButton } from './PillButton';
import { Segmented } from './Segmented';

/**
 * One joinable contest. The important change from the first build: **entry is a
 * control inside the card, not a separate card**.
 *
 * The old version rendered the difficulty × entry cross-product, so Solo Pools
 * showed nine cards where three sentences repeated verbatim and only the dollar
 * amount differed. A stake is a parameter of a contest, not a different
 * contest. Picking an entry here updates the payout in place, and the grid drops
 * from nine cards to three (16-ui-revamp-plan §1).
 *
 * The headline is the **clear bar**: the number to beat, drawn against your own
 * baseline. That is the product's actual idea, and it says what "Clears ≈ 20% of
 * the time" was trying to say without a sentence.
 */
export function WagerCard({
  gameName,
  tag,
  title,
  subtitle,
  target,
  clearRate,
  lowerIsBetter = false,
  targetUnit,
  targetNote,
  entryOptions,
  payoutFor,
  payoutLabel,
  capacity,
  filled,
  oneVsOne = false,
  feeNote,
  speedOptions,
  selectedSpeed,
  onSpeedChange,
  buttonLabel,
  onJoin,
  disabled = false,
  joining = false,
  requireConfirm = false,
}: {
  gameName: string;
  /** Difficulty, field size, or speed. One word where possible. */
  tag?: string;
  title: string;
  /** One short line. Not a paragraph. */
  subtitle?: string;
  /** The number to beat. Omitted for markets with no bar (e.g. win the game). */
  target?: number | null;
  /** Server's estimate (0..1) of how often you clear that bar. */
  clearRate?: number | null;
  /** True when a smaller number wins (fewest moves), so the copy flips. */
  lowerIsBetter?: boolean;
  /** What the headline number counts, e.g. "moves". */
  targetUnit?: string;
  /**
   * One short qualifier under the bar, for a condition the number alone cannot
   * carry. "14 moves or fewer" reads as though any short game counts, so a
   * win-only metric has to say so or a player who loses in ten is entitled to
   * think they cleared it.
   */
  targetNote?: string;
  entryOptions: number[];
  /** Derived payout for the selected entry. */
  payoutFor: (entryCents: number) => number;
  payoutLabel: string;
  capacity: number;
  /** Synthetic "seats filled" count. Demo-only — omit it in authenticated
   * production, where pools/tournaments form via matchmaking and there is no
   * real roster to read, so no fabricated count is shown. */
  filled?: number;
  oneVsOne?: boolean;
  /**
   * Optional pre-commit fee disclosure shown below the payout, computed from the
   * selected entry so it shows real dollars (e.g. "$2.00 platform fee"). The
   * rake must always be visible before commit on every joinable surface
   * (design-guidelines §8).
   */
  feeNote?: (entryCents: number) => string;
  /** Speed options for speed-gated markets (chess). Shows a picker if > 1. */
  speedOptions?: string[];
  selectedSpeed?: string;
  onSpeedChange?: (speed: string) => void;
  buttonLabel: string;
  onJoin: (entryCents: number) => void;
  disabled?: boolean;
  joining?: boolean;
  /** Two-step join: the first click reveals a confirm button under the card
   * (for money-commitment contests you can't back out of once matched). */
  requireConfirm?: boolean;
}) {
  // Default to the middle preset: the one most people pick, and it makes the
  // segmented control's purpose obvious at a glance.
  const [entry, setEntry] = useState(
    () => entryOptions[Math.floor(entryOptions.length / 2)] ?? entryOptions[0],
  );
  const selected = entryOptions.includes(entry) ? entry : entryOptions[0];
  // Armed = the first tap happened; a confirm button is showing beneath.
  const [armed, setArmed] = useState(false);

  return (
    <Card className="flex flex-col p-4" interactive>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-text-secondary">{gameName}</span>
        {tag && (
          <span className="rounded-pill bg-panel-raised px-2 py-0.5 text-micro font-semibold capitalize text-text-secondary">
            {tag}
          </span>
        )}
      </div>

      <h3 className="mt-3 text-lg font-semibold leading-tight text-text">{title}</h3>

      {target != null ? (
        <div className="mt-4">
          <div className="mb-2 flex items-baseline gap-2">
            <span className="text-3xl font-semibold text-text">
              {Number.isInteger(target) ? target : target.toFixed(2)}
            </span>
            <span className="text-xs text-text-secondary">
              {targetUnit ? `${targetUnit} ` : ''}
              {lowerIsBetter ? 'or fewer' : 'or better'}
            </span>
          </div>
          {clearRate != null && <ClearRate rate={clearRate} />}
          {targetNote && (
            <p className="mt-2 text-xs text-text-secondary">{targetNote}</p>
          )}
        </div>
      ) : (
        subtitle && <p className="mt-3 text-sm text-text-secondary">{subtitle}</p>
      )}

      {speedOptions && speedOptions.length > 1 && selectedSpeed && onSpeedChange && (
        <div className="mt-3 flex items-center gap-2">
          <span className="text-xs text-text-secondary">Speed</span>
          <div className="flex flex-wrap gap-1">
            {speedOptions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => onSpeedChange(s)}
                className={[
                  'rounded-pill px-2 py-0.5 text-xs font-medium capitalize transition',
                  selectedSpeed === s
                    ? 'bg-action text-bg'
                    : 'bg-panel-raised text-text-secondary hover:text-text',
                ].join(' ')}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-5">
        <p className="label-money mb-2">Entry</p>
        <Segmented
          size="sm"
          ariaLabel={`Entry for ${title}`}
          options={entryOptions.map((cents) => ({
            value: cents,
            label: formatCurrency(cents),
          }))}
          value={selected}
          onChange={setEntry}
        />
      </div>

      <div className="mt-4 flex items-end justify-between gap-3">
        <div>
          <p className="label-money">{payoutLabel}</p>
          <p className="text-lg font-semibold text-green">
            {formatCurrency(payoutFor(selected))}
          </p>
          {feeNote && (
            <p className="mt-0.5 text-xs text-text-secondary">{feeNote(selected)}</p>
          )}
        </div>
        {(oneVsOne || filled != null) && (
          <p className="text-xs text-text-tertiary">
            {oneVsOne ? '1v1' : `${filled} of ${capacity} in`}
          </p>
        )}
      </div>

      <div className="mt-4">
        {requireConfirm && armed && !disabled ? (
          // Second step: a confirm button pops up under the card. No blurb —
          // the amount is on the button, and the commitment is the whole point.
          <div className="flex flex-col gap-2">
            <PillButton
              className="mm-glow"
              fullWidth
              size="lg"
              disabled={joining}
              onClick={() => {
                onJoin(selected);
                setArmed(false);
              }}
            >
              {joining ? 'Joining…' : `Confirm · ${formatCurrency(selected)}`}
            </PillButton>
            <PillButton
              fullWidth
              size="sm"
              variant="text"
              disabled={joining}
              onClick={() => setArmed(false)}
            >
              Cancel
            </PillButton>
          </div>
        ) : (
          <PillButton
            className="mm-glow"
            fullWidth
            size="lg"
            disabled={disabled || joining}
            onClick={() => (requireConfirm ? setArmed(true) : onJoin(selected))}
          >
            {joining ? 'Joining…' : buttonLabel}
          </PillButton>
        )}
      </div>
    </Card>
  );
}
