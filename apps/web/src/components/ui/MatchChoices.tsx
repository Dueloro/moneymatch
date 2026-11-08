import {
  clockFor,
  clockLabel,
  speedName,
  type SpeedClock,
} from '../../lib/timeControl';
import { AmountText, PointsFigure } from './AmountText';
import { Segmented } from './Segmented';

export function TimeControlChoice({
  speeds,
  clocks,
  value,
  onChange,
}: {
  speeds: string[];
  clocks?: SpeedClock[];
  value: string;
  onChange: (speed: string) => void;
}) {
  return (
    <div>
      <p className="label-neutral mb-2">Time control</p>
      <Segmented
        size="lg"
        fullWidth
        ariaLabel="Time control"
        options={speeds.map((s) => ({
          value: s,
          label: (
            <span className="flex flex-col items-center leading-tight">
              <span>{speedName(s)}</span>
              {clockLabel(clockFor(s, clocks)) && (
                <span className="num text-micro font-medium text-text-tertiary">
                  {clockLabel(clockFor(s, clocks))}
                </span>
              )}
            </span>
          ),
        }))}
        value={value}
        onChange={onChange}
      />
    </div>
  );
}

export function StakeChoice({
  presets,
  value,
  onChange,
}: {
  presets: readonly number[];
  value: number;
  onChange: (cents: number) => void;
}) {
  return (
    <div>
      <p className="label-money mb-2">Stake</p>
      <Segmented
        size="lg"
        fullWidth
        ariaLabel="Stake"
        options={presets.map((cents) => ({
          value: cents,
          label: (
            <span className="num">
              <PointsFigure cents={cents} />
            </span>
          ),
        }))}
        value={value}
        onChange={onChange}
      />
    </div>
  );
}

export function PayoutSummary({ prize, fee }: { prize: number; fee: number }) {
  return (
    <div>
      <p className="label-money">Winner takes</p>
      <p className="text-3xl font-semibold" data-testid="desk-prize">
        <AmountText cents={prize} signed={false} money />
      </p>
      <p className="mt-1 text-xs text-text-secondary">
        Fee{' '}
        <span className="num text-red">
          <PointsFigure cents={fee} />
        </span>{' '}
        · a draw refunds both
      </p>
    </div>
  );
}
