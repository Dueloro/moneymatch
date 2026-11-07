import type { ReactNode } from 'react';

export function CardGrid({ count, children }: { count: number; children: ReactNode }) {
  const cols =
    count <= 1
      ? 'grid-cols-1 max-w-sm'
      : count === 2
        ? 'grid-cols-1 sm:grid-cols-2 max-w-3xl'
        : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3';
  return <div className={`grid gap-4 ${cols}`}>{children}</div>;
}
