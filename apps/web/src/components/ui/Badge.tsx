/**
 * The one count badge (16-ui-revamp-plan §1), replacing the three treatments the
 * inventory found: the nav's bare dot, the sub-tab pill, and the conversation
 * list's larger glowing pill.
 *
 * It is never lime. An unread count is not money, so it uses the paper action
 * tone, which also keeps it legible at 11px.
 */
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
        'bg-action px-1.5 text-micro font-semibold text-bg',
        className,
      ].join(' ')}
    >
      {count > 99 ? '99+' : count}
    </span>
  );
}

/** The dot form, for places with no room for a number (the nav bell). */
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
