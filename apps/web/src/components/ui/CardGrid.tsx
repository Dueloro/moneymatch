import type { ReactNode } from 'react';

export function CardGrid({ count, children }: { count: number; children: ReactNode }) {
  const cols =
    count <= 1
      ? 'grid-cols-1 max-w-sm'
      : count === 2
        ? 'grid-cols-[repeat(auto-fill,minmax(18rem,1fr))] max-w-3xl'
        : 'grid-cols-[repeat(auto-fill,minmax(18rem,1fr))]';
  return <div className={`grid gap-4 ${cols}`}>{children}</div>;
}
