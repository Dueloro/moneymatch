import { useEffect, useRef, type ReactNode } from 'react';

import { Card } from './Card';

/**
 * A panel anchored under its trigger that floats above the page instead of
 * displacing it.
 *
 * The browse pages' explainer and filter controls were both inline disclosures,
 * so opening either one pushed the whole contest grid down the screen and the
 * cards you were reading moved out from under the cursor. That was tolerable
 * when the page scrolled; now that the shell is locked to the viewport the grid
 * has nowhere to go, so both live up here instead.
 *
 * Closes on outside pointer-down and on Escape. The caller owns `open` so the
 * trigger can carry `aria-expanded` and its own active styling.
 */
export function Popover({
  open,
  onClose,
  id,
  align = 'end',
  panelClassName = 'w-80',
  trigger,
  children,
}: {
  open: boolean;
  onClose: () => void;
  /** Ties the trigger's `aria-controls` to the panel. */
  id: string;
  /** Which edge the panel lines up with. `end` hangs it leftwards off the right
   * edge, which is what a right-aligned trigger needs to stay on screen. */
  align?: 'start' | 'end';
  panelClassName?: string;
  trigger: ReactNode;
  children: ReactNode;
}) {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    // pointerdown rather than click, so the panel is already gone by the time a
    // click lands on whatever is underneath it.
    const onPointerDown = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) onClose();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, onClose]);

  return (
    <div ref={root} className="relative">
      {trigger}
      {open && (
        <Card
          tone="overlay"
          id={id}
          role="dialog"
          className={[
            'absolute top-[calc(100%+0.5rem)] z-30 max-w-[calc(100vw-2rem)] p-4',
            align === 'end' ? 'right-0' : 'left-0',
            panelClassName,
          ].join(' ')}
        >
          {children}
        </Card>
      )}
    </div>
  );
}
