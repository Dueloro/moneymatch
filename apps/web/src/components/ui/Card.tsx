import type { ReactNode } from 'react';

/**
 * The one card primitive (16-ui-revamp-plan §4). Every surface that sits on the
 * page is this: `--radius-card`, a 1px hairline, the `panel` fill, no shadow.
 * Depth comes from the surface ramp and the border, never from a drop shadow.
 *
 * Replaces the four radii and the bordered/borderless split the inventory found
 * (§14): if it's on the page it's a Card, if it's inside a Card it's an inset,
 * if it floats above the page it's an `overlay` tone.
 */
export function Card({
  children,
  tone = 'default',
  interactive = false,
  className = '',
  as: Tag = 'div',
  ...rest
}: {
  children: ReactNode;
  /** `overlay` is for dialogs and menus: stronger edge, the one shadow token. */
  tone?: 'default' | 'raised' | 'overlay';
  /** Adds the hover edge. Use on cards that are themselves a click target. */
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
