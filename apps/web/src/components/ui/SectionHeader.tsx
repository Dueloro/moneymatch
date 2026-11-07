import type { ReactNode } from 'react';

export function SectionHeader({
  level = 'section',
  children,
  hint,
  action,
  className = '',
}: {
  level?: 'page' | 'section' | 'sub';
  children: ReactNode;
  hint?: ReactNode;
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
