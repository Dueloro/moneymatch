/** `inline` renders a span so it can sit inside text (a loading figure). */
export function Skeleton({
  className = '',
  inline = false,
  testId,
}: {
  className?: string;
  inline?: boolean;
  testId?: string;
}) {
  const Tag = inline ? 'span' : 'div';
  return (
    <Tag
      aria-hidden
      data-testid={testId}
      className={`animate-pulse rounded-inset bg-panel-raised ${inline ? 'inline-block' : ''} ${className}`}
    />
  );
}

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

export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div data-testid="skeleton-list">
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  );
}
