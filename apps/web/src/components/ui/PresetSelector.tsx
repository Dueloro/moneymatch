import { formatCurrency } from '../../lib/format';

/**
 * Row of $-preset pills (add funds, cash out). Server-defined amounts only; the
 * client never invents a value.
 *
 * Selection is structural, a raised surface with a strong edge, so a chosen
 * amount can't be mistaken for a money *figure* (16-ui-revamp-plan §2). For the
 * entry amount inside a contest card, use `Segmented` instead.
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
            aria-pressed={active}
            onClick={() => onSelect(cents)}
            className={[
              'rounded-pill border px-4 py-2 text-sm font-semibold transition-colors',
              'disabled:cursor-not-allowed disabled:opacity-40',
              active
                ? 'border-line-strong bg-panel-raised text-text'
                : 'border-hairline text-text-secondary hover:border-line-strong hover:text-text',
            ].join(' ')}
          >
            {formatCurrency(cents)}
          </button>
        );
      })}
    </div>
  );
}
