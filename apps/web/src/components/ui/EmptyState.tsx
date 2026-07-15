import type { ReactNode } from 'react';

/** Honest empty state (no seeded/bot content — 11-migration §3). */
export function EmptyState({
  title,
  subline,
  action,
}: {
  title: string;
  subline?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-24 text-center">
      <p className="text-lg font-semibold text-text">{title}</p>
      {subline && <p className="max-w-sm text-sm text-text-secondary">{subline}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
