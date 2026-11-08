import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';

import { PillButton } from './PillButton';

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

/** Bottom sheet below md, centred panel at md+. Mount it to open, unmount to close. */
export function Dialog({
  title,
  onClose,
  children,
  className = '',
  testId,
  width = 'md:max-w-md',
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  className?: string;
  testId?: string;
  width?: string;
}) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    const { overflow } = document.body.style;
    document.body.style.overflow = 'hidden';
    const first = panel.current?.querySelector<HTMLElement>(
      `[data-autofocus],${FOCUSABLE.split(',')
        .map((s) => `${s}:not([data-dialog-close])`)
        .join(',')}`,
    );
    (first ?? panel.current)?.focus();
    const frame = requestAnimationFrame(() => setEntered(true));
    return () => {
      cancelAnimationFrame(frame);
      document.body.style.overflow = overflow;
      trigger?.focus?.();
    };
  }, []);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== 'Tab') return;
    const items = Array.from(
      panel.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [],
    );
    if (items.length === 0) {
      e.preventDefault();
      return;
    }
    const firstEl = items[0];
    const lastEl = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === firstEl || active === panel.current)) {
      e.preventDefault();
      lastEl.focus();
    } else if (!e.shiftKey && active === lastEl) {
      e.preventDefault();
      firstEl.focus();
    }
  }

  return createPortal(
    <div
      className={[
        'fixed inset-0 z-50 flex items-end justify-center bg-black/70 md:items-center md:p-4',
        'motion-safe:transition-opacity motion-safe:duration-200',
        entered ? 'opacity-100' : 'opacity-0 motion-reduce:opacity-100',
      ].join(' ')}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      onKeyDown={onKeyDown}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        data-testid={testId}
        className={[
          'flex max-h-[90vh] w-full flex-col overflow-hidden rounded-t-card border border-hairline bg-overlay shadow-overlay outline-none md:rounded-card',
          width,
          'motion-safe:transition-transform motion-safe:duration-200',
          entered
            ? 'translate-y-0'
            : 'translate-y-8 motion-reduce:translate-y-0 md:translate-y-2',
          className,
        ].join(' ')}
      >
        <div className="flex items-start justify-between gap-4 px-5 pt-5 md:px-6">
          <h3 id={titleId} className="text-lg font-bold text-text">
            {title}
          </h3>
          <PillButton
            variant="text"
            className="!px-2"
            onClick={onClose}
            data-dialog-close
          >
            Close
          </PillButton>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
