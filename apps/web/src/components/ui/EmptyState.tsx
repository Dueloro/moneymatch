import type { ReactNode } from 'react';

/**
 * Empty states are invitations, not apologies: a plain title, one line of
 * context, and a way forward. No seeded or bot content anywhere.
 */
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
    <div className="flex flex-col items-center justify-center gap-2 rounded-card border border-dashed border-hairline px-6 py-16 text-center">
      <p className="text-base font-semibold text-text">{title}</p>
      {subline && <p className="max-w-sm text-sm text-text-secondary">{subline}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
