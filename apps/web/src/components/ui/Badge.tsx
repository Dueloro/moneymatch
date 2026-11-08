export function Badge({
  count,
  className = '',
}: {
  count: number;
  className?: string;
}) {
  if (count <= 0) return null;
  return (
    <span
      className={[
        'inline-flex min-w-[1.25rem] items-center justify-center rounded-pill',
        'bg-action px-1.5 text-micro font-semibold tabular-nums text-bg',
        className,
      ].join(' ')}
    >
      {count > 99 ? '99+' : count}
    </span>
  );
}

export function BadgeDot({
  show,
  className = '',
  testId,
}: {
  show: boolean;
  className?: string;
  testId?: string;
}) {
  if (!show) return null;
  return (
    <span
      data-testid={testId}
      className={['h-2 w-2 rounded-full bg-action', className].join(' ')}
    />
  );
}
