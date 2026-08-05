import { useCallback, useState, type ReactNode } from 'react';

import { MenuIcon } from './icons';
import { PillButton } from './PillButton';
import { Popover } from './Popover';

/** Sentinel for "no filter on this dimension" across the browse pages. */
export const ALL = 'all';

/** A single row of filter chips: an "All" option plus one chip per value. */
export function FilterChips<T extends string | number>({
  label,
  options,
  selected,
  onSelect,
  format,
}: {
  label: string;
  options: T[];
  selected: T | typeof ALL;
  onSelect: (value: T | typeof ALL) => void;
  format?: (value: T) => string;
}) {
  const chip = (active: boolean) =>
    [
      'rounded-pill border px-3 py-1 text-xs font-semibold transition-colors',
      active
        ? 'border-line-strong bg-panel-raised text-text'
        : 'border-hairline text-text-secondary hover:border-line-strong hover:text-text',
    ].join(' ');
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-medium text-text-tertiary">{label}</span>
      <button
        type="button"
        aria-pressed={selected === ALL}
        className={chip(selected === ALL)}
        onClick={() => onSelect(ALL)}
      >
        All
      </button>
      {options.map((o) => (
        <button
          key={String(o)}
          type="button"
          aria-pressed={selected === o}
          className={`${chip(selected === o)} capitalize`}
          onClick={() => onSelect(o)}
        >
          {format ? format(o) : String(o)}
        </button>
      ))}
    </div>
  );
}

/**
 * A hamburger-toggled filter panel shared by the browse pages. Owns its own
 * open/closed state and renders the caller's `FilterChips` rows as children,
 * plus a "Clear filters" action when any filter is active.
 *
 * It lives in the page heading's action slot, opposite the title, and drops its
 * panel as a `Popover` — opening it used to push every card down the screen.
 */
export function FilterBar({
  testId,
  activeCount,
  onClear,
  children,
}: {
  testId: string;
  activeCount: number;
  onClear: () => void;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);

  return (
    <Popover
      open={open}
      onClose={close}
      id={`${testId}-panel`}
      trigger={
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls={`${testId}-panel`}
          className="inline-flex items-center gap-2 rounded-pill border border-hairline px-3 py-1.5 text-xs font-semibold text-text-secondary transition-colors hover:border-line-strong hover:text-text"
          data-testid={`${testId}-toggle`}
        >
          <MenuIcon className="h-4 w-4" />
          Filters
          {activeCount > 0 && (
            <span className="rounded-pill bg-action px-1.5 text-micro font-semibold text-bg">
              {activeCount}
            </span>
          )}
        </button>
      }
    >
      <div className="flex flex-col gap-3" data-testid={testId}>
        {children}
        {activeCount > 0 && (
          <div>
            <PillButton variant="text" size="sm" onClick={onClear}>
              Clear filters
            </PillButton>
          </div>
        )}
      </div>
    </Popover>
  );
}
