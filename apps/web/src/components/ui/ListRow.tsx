import type { ReactNode } from 'react';

/** Used by the ledger, waiting/friends/activity/inbox lists. */
export function ListRow({
  left,
  title,
  subline,
  right,
  footer,
}: {
  left?: ReactNode;
  title: ReactNode;
  subline?: ReactNode;
  right?: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="border-b border-hairline py-3 last:border-b-0">
      <div className="flex items-center gap-3">
        {left}
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-text">{title}</div>
          {subline && (
            <div className="truncate text-xs text-text-secondary">{subline}</div>
          )}
        </div>
        {right && (
          <div className="flex shrink-0 items-center text-sm touch:min-h-11">
            {right}
          </div>
        )}
      </div>
      {footer && <div className="mt-2 pl-[1.375rem]">{footer}</div>}
    </div>
  );
}
