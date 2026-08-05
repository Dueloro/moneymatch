import type { ReactNode } from 'react';

/**
 * The browse grid. Columns are capped by the number of cards, so one contest
 * doesn't sit alone in the top-left of a three-column grid looking like a
 * loading error. With entry moved inside the card (plan §1) these grids are
 * small by design, and the layout has to hold up at two or three items.
 */
export function CardGrid({ count, children }: { count: number; children: ReactNode }) {
  const cols =
    count <= 1
      ? 'grid-cols-1 max-w-sm'
      : count === 2
        ? 'grid-cols-1 sm:grid-cols-2 max-w-3xl'
        : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3';
  return <div className={`grid gap-4 ${cols}`}>{children}</div>;
}
