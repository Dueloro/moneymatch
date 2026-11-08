import type { ReactNode } from 'react';

export function Card({
  children,
  tone = 'default',
  interactive = false,
  className = '',
  as: Tag = 'div',
  ...rest
}: {
  children: ReactNode;
  tone?: 'default' | 'raised' | 'overlay';
  interactive?: boolean;
  className?: string;
  as?: 'div' | 'section' | 'article' | 'aside' | 'li';
} & Record<string, unknown>) {
  const tones = {
    default: 'bg-panel border-hairline',
    raised: 'bg-panel-raised border-hairline',
    overlay: 'bg-overlay border-line-strong shadow-overlay',
  };
  return (
    <Tag
      className={[
        'rounded-card border',
        tones[tone],
        interactive ? 'transition-colors hover:border-line-strong' : '',
        className,
      ].join(' ')}
      {...rest}
    >
      {children}
    </Tag>
  );
}
