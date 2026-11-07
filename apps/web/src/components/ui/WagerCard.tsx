import { useState } from 'react';

import { formatPoints } from '../../lib/format';
import { AmountText, PointsFigure } from './AmountText';
import { Card } from './Card';
import { ClearRate } from './ClearBar';
import { PillButton } from './PillButton';
import { Segmented } from './Segmented';

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
  tag?: string;
  title: string;
  subtitle?: string;
  target?: number | null;
  clearRate?: number | null;
  lowerIsBetter?: boolean;
  targetUnit?: string;
  targetNote?: string;
  entryOptions: number[];
  payoutFor: (entryCents: number) => number;
  payoutLabel: string;
  oneVsOne?: boolean;
  /**
   * The rake must always be visible before commit on every joinable surface.
   */
  feeNote?: (entryCents: number) => string;
  speedOptions?: string[];
  selectedSpeed?: string;
  onSpeedChange?: (speed: string) => void;
  buttonLabel: string;
  onJoin: (entryCents: number) => void;
  disabled?: boolean;
  joining?: boolean;
  requireConfirm?: boolean;
}) {
  const [entry, setEntry] = useState(
    () => entryOptions[Math.floor(entryOptions.length / 2)] ?? entryOptions[0],
  );
  const selected = entryOptions.includes(entry) ? entry : entryOptions[0];
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
            <span className="num text-3xl font-semibold text-text">
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
            label: (
              <span className="num">
                <PointsFigure cents={cents} />
              </span>
            ),
          }))}
          value={selected}
          onChange={setEntry}
        />
      </div>

      <div className="mt-4 flex items-end justify-between gap-3">
        <div>
          <p className="label-money">{payoutLabel}</p>
          <p className="text-lg font-semibold">
            <AmountText cents={payoutFor(selected)} signed={false} money />
          </p>
          {feeNote && (
            <p className="mt-0.5 text-xs text-text-secondary">{feeNote(selected)}</p>
          )}
        </div>
        {oneVsOne && <p className="text-xs text-text-tertiary">1v1</p>}
      </div>

      <div className="mt-4">
        {requireConfirm && armed && !disabled ? (
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
              {joining ? 'Joining…' : `Confirm · ${formatPoints(selected)}`}
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
