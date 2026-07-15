import { formatCurrency } from '../../lib/format';

/**
 * Row of $-preset pills (Add-funds, entry presets). Server-defined amounts only;
 * the client never invents a value. Selected pill = green outline (02-design §2).
 */
export function PresetSelector({
  presetsCents,
  selectedCents,
  onSelect,
  disabled = false,
}: {
  presetsCents: readonly number[];
  selectedCents?: number | null;
  onSelect: (cents: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {presetsCents.map((cents) => {
        const active = cents === selectedCents;
        return (
          <button
            key={cents}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(cents)}
            className={[
              'rounded-pill border px-4 py-2 text-sm font-semibold transition',
              'disabled:cursor-not-allowed disabled:opacity-40',
              active
                ? 'border-green text-green'
                : 'border-hairline text-text hover:border-text-secondary',
            ].join(' ')}
          >
            {formatCurrency(cents)}
          </button>
        );
      })}
    </div>
  );
}
