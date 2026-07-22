/** Pulsing placeholder block. Compose these into skeleton rows/cards while a
 * query loads, instead of bare "Loading…" text. */
export function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={`animate-pulse rounded-md bg-panel-raised ${className}`}
    />
  );
}

/** A list-row-shaped skeleton (title + subline + right slot), matching ListRow. */
export function SkeletonRow() {
  return (
    <div className="flex items-center justify-between border-b border-hairline py-4">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-3.5 w-32" />
        <Skeleton className="h-3 w-20" />
      </div>
      <Skeleton className="h-3.5 w-16" />
    </div>
  );
}

/** A stack of skeleton rows. */
export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div data-testid="skeleton-list">
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  );
}
