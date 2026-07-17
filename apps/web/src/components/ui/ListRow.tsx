import type { ReactNode } from 'react';

/**
 * Generic list row (02-design §5): optional left slot, title + subline, and a
 * right slot. Hairline-separated by the containing list. Used by the ledger,
 * waiting/friends/activity/inbox lists.
 */
export function ListRow({
  left,
  title,
  subline,
  right,
}: {
  left?: ReactNode;
  title: ReactNode;
  subline?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 border-b border-hairline py-3 last:border-b-0">
      {left}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-text">{title}</div>
        {subline && (
          <div className="truncate text-xs text-text-secondary">{subline}</div>
        )}
      </div>
      {right && <div className="shrink-0 text-sm">{right}</div>}
    </div>
  );
}
