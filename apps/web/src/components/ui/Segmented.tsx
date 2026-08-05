import type { ReactNode } from 'react';

export interface SegmentOption<T extends string | number> {
  value: T;
  label: ReactNode;
  /** Optional count rendered after the label (sub-tabs). */
  badge?: number;
}

/**
 * One segmented control, used for every "pick one of a few" in the product: the
 * contest-mode switcher, the entry amount inside a card, and the Social
 * sub-tabs. Selection is structural (a raised pill on a recessed track), never
 * a hue, so it never competes with money or with the primary action.
 *
 * Renders as a real tablist so keyboard and screen-reader behaviour is correct.
 */
export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  size = 'md',
  fullWidth = false,
  ariaLabel,
  renderBadge,
}: {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: 'sm' | 'md';
  fullWidth?: boolean;
  ariaLabel?: string;
  renderBadge?: (badge: number) => ReactNode;
}) {
  const pad = size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-1.5 text-sm';
  return (
    <div
      role="tablist"
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
            role="tab"
            aria-selected={active}
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
