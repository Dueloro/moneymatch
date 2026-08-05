import { useCallback, useState, type ReactNode } from 'react';

import { useDismissed } from '../../hooks/useDismissed';
import { Popover } from './Popover';

/**
 * "How it works": the browse pages' explainer prose, demoted from a permanent
 * grey wall to an affordance (16-ui-revamp-plan §1). Open on a player's first
 * visit to a surface, closed and remembered forever after. The copy still
 * exists; it just stops being rent.
 *
 * It sits at the top right of the browse header and opens as a `Popover`, so
 * reading it no longer shoves the contest grid down the page.
 */
export function HowItWorks({
  id,
  children,
  label = 'How it works',
}: {
  /** Storage key, unique per surface. */
  id: string;
  children: ReactNode;
  label?: string;
}) {
  const panelId = `how-${id}`;
  const [dismissed, dismiss] = useDismissed(`howitworks.${id}`);
  const [open, setOpen] = useState(!dismissed);

  const close = useCallback(() => {
    dismiss();
    setOpen(false);
  }, [dismiss]);

  return (
    <Popover
      open={open}
      onClose={close}
      id={panelId}
      trigger={
        <button
          type="button"
          onClick={() => (open ? close() : setOpen(true))}
          aria-expanded={open}
          aria-controls={panelId}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-text-secondary transition-colors hover:text-text"
        >
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" aria-hidden>
            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth={1.6} />
            <path
              d="M12 11v5M12 8h.01"
              stroke="currentColor"
              strokeWidth={1.8}
              strokeLinecap="round"
            />
          </svg>
          {label}
        </button>
      }
    >
      <p className="text-sm leading-relaxed text-text-secondary">{children}</p>
    </Popover>
  );
}
