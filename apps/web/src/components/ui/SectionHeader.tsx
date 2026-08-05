import type { ReactNode } from 'react';

/**
 * The one heading component (16-ui-revamp-plan §3), replacing the three styles
 * the inventory found competing at the same rank: `.label-mono`, the 12px
 * uppercase tertiary label on Profile, and Wallet's 14px semibold.
 *
 * Three levels only. The mono uppercase treatment is gone from headings entirely
 * and survives only as `.label-money`, the caption above a currency figure.
 */
export function SectionHeader({
  level = 'section',
  children,
  hint,
  action,
  className = '',
}: {
  level?: 'page' | 'section' | 'sub';
  children: ReactNode;
  /** One line of supporting copy under the heading. */
  hint?: ReactNode;
  /** Right-aligned slot: a filter toggle, a "see all" link. */
  action?: ReactNode;
  className?: string;
}) {
  const Tag = level === 'page' ? 'h1' : level === 'section' ? 'h2' : 'h3';
  const size = {
    page: 'text-2xl font-semibold text-text',
    section: 'text-xl font-semibold text-text',
    sub: 'text-sm font-semibold text-text',
  }[level];

  return (
    <div
      className={[
        'flex items-start justify-between gap-4',
        level === 'page' ? 'mb-6' : 'mb-3',
        className,
      ].join(' ')}
    >
      <div className="min-w-0">
        <Tag className={size}>{children}</Tag>
        {hint && <p className="mt-1 text-xs text-text-secondary">{hint}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
