import type { ReactNode } from 'react';

export interface SegmentOption<T extends string | number> {
  value: T;
  label: ReactNode;
  badge?: number;
}

export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  size = 'md',
  fullWidth = false,
  ariaLabel,
  renderBadge,
  selectionRole = 'tablist',
}: {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: 'sm' | 'md' | 'lg';
  fullWidth?: boolean;
  ariaLabel?: string;
  renderBadge?: (badge: number) => ReactNode;
  selectionRole?: 'tablist' | 'radiogroup';
}) {
  const pad = {
    sm: 'px-2.5 py-1 text-xs touch:min-h-11',
    md: 'px-3.5 py-1.5 text-sm touch:min-h-11',
    lg: 'min-h-11 px-2 py-2 text-sm sm:px-4',
  }[size];
  return (
    <div
      role={selectionRole}
      aria-label={ariaLabel}
      className={[
        'inline-flex gap-1 rounded-pill border border-hairline bg-panel p-1',
        fullWidth ? 'flex w-full' : '',
      ].join(' ')}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={String(option.value)}
            type="button"
            role={selectionRole === 'radiogroup' ? 'radio' : 'tab'}
            aria-selected={selectionRole === 'tablist' ? active : undefined}
            aria-checked={selectionRole === 'radiogroup' ? active : undefined}
            onClick={() => onChange(option.value)}
            className={[
              'inline-flex items-center justify-center gap-2 rounded-pill font-semibold',
              'transition-colors',
              pad,
              fullWidth ? 'flex-1' : '',
              active
                ? 'bg-panel-raised text-text shadow-[inset_0_0_0_1px_var(--line-strong)]'
                : 'text-text-secondary hover:text-text',
            ].join(' ')}
          >
            {option.label}
            {option.badge != null &&
              option.badge > 0 &&
              (renderBadge ? renderBadge(option.badge) : null)}
          </button>
        );
      })}
    </div>
  );
}
