import { useId, useState, type ReactNode } from 'react';

import { ChevronDownIcon } from './icons';

/**
 * A self-contained card row with an optional expandable body — the app's
 * standard "line item you can open to learn more" (02-design §5, cards
 * refresh). Collapsed it reads like a `ListRow` (left slot, title + subline,
 * right slot); when `children` are provided a chevron appears and the header
 * toggles a detail panel. `footer` renders under the header in both states
 * (e.g. an Activity live line).
 *
 * Non-expandable (no `children`) it's just a styled card, so the same component
 * serves every list across the app.
 */
export function ExpandableCard({
  left,
  title,
  subline,
  right,
  footer,
  children,
  defaultOpen = false,
  ariaLabel,
}: {
  left?: ReactNode;
  title: ReactNode;
  subline?: ReactNode;
  right?: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
  defaultOpen?: boolean;
  ariaLabel?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  const expandable = children != null && children !== false;

  const header = (
    <>
      {left}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-text">{title}</div>
        {subline && <div className="text-xs text-text-secondary">{subline}</div>}
      </div>
      {right && <div className="shrink-0 text-sm">{right}</div>}
      {expandable && (
        <ChevronDownIcon
          className={`h-4 w-4 shrink-0 text-text-secondary transition-transform ${
            open ? 'rotate-180' : ''
          }`}
        />
      )}
    </>
  );

  return (
    <div className="rounded-2xl border border-hairline bg-panel transition hover:border-text-secondary/40">
      {expandable ? (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          aria-label={ariaLabel}
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left"
        >
          {header}
        </button>
      ) : (
        <div className="flex items-center gap-3 px-4 py-3">{header}</div>
      )}

      {footer && <div className="px-4 pb-3 pl-[calc(1rem+1.375rem)]">{footer}</div>}

      {expandable && open && (
        <div id={panelId} className="border-t border-hairline px-4 py-3">
          {children}
        </div>
      )}
    </div>
  );
}
