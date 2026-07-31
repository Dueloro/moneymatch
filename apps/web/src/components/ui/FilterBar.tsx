import { useState, type ReactNode } from 'react';

import { MenuIcon } from './icons';
import { PillButton } from './PillButton';

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
      'rounded-pill border px-3 py-1 text-xs font-semibold transition',
      active
        ? 'bg-panel-raised text-text border-text-secondary'
        : 'border-hairline text-text-secondary hover:text-text',
    ].join(' ');
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="label-mono text-text-secondary">{label}</span>
      <button className={chip(selected === ALL)} onClick={() => onSelect(ALL)}>
        All
      </button>
      {options.map((o) => (
        <button
          key={String(o)}
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
 * A hamburger-toggled filter panel shared by the browse pages (pools, H2H,
 * tournaments). Owns its own open/closed state and renders the caller's
 * `FilterChips` rows as children, plus a "Clear filters" action when any
 * filter is active. `testId` names the panel and its toggle
 * (`<testId>-toggle`) so each page's tests can target its own bar.
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
  return (
    <div className="mb-6">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={testId}
        className="inline-flex items-center gap-2 rounded-pill border border-hairline px-3 py-1.5 text-xs font-semibold text-text-secondary transition hover:text-text"
        data-testid={`${testId}-toggle`}
      >
        <MenuIcon className="h-4 w-4" />
        Filters
        {activeCount > 0 && (
          <span className="rounded-pill bg-green px-1.5 text-[10px] font-bold text-black">
            {activeCount}
          </span>
        )}
      </button>
      {open && (
        <div
          id={testId}
          className="mt-3 flex flex-col gap-3 rounded-2xl bg-panel p-4"
          data-testid={testId}
        >
          {children}
          {activeCount > 0 && (
            <div>
              <PillButton variant="text" onClick={onClear}>
                Clear filters
              </PillButton>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
