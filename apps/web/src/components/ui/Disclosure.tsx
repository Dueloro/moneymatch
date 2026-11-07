import { useCallback, useState, type ReactNode } from 'react';

import { Popover } from './Popover';

function InfoIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 shrink-0" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth={1.6} />
      <path
        d="M12 11v5M12 8h.01"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Closed by default; opens a compact panel under its trigger. */
export function HowItWorks({
  id,
  children,
  label = 'How it works',
}: {
  id: string;
  children: ReactNode;
  label?: string;
}) {
  const panelId = `how-${id}`;
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);

  return (
    <Popover
      open={open}
      onClose={close}
      id={panelId}
      panelClassName="w-72"
      trigger={
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls={panelId}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-text-secondary transition-colors hover:text-text"
        >
          <InfoIcon />
          {label}
        </button>
      }
    >
      <p className="text-sm leading-relaxed text-text-secondary">{children}</p>
    </Popover>
  );
}

/** The same explainer, inline in the page flow, for a first visit. */
export function HowItWorksNote({
  children,
  onDismiss,
}: {
  children: ReactNode;
  onDismiss: () => void;
}) {
  return (
    <div
      role="note"
      className="flex items-start gap-2 text-sm leading-snug text-text-secondary"
    >
      <span className="mt-[3px] text-text-tertiary">
        <InfoIcon />
      </span>
      <p className="min-w-0 flex-1">{children}</p>
      <button
        type="button"
        onClick={onDismiss}
        className="shrink-0 text-xs font-semibold text-text transition-colors hover:text-text-secondary"
      >
        Got it
      </button>
    </div>
  );
}
