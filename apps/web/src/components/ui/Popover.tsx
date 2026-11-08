import { useEffect, useRef, type ReactNode } from 'react';

import { Card } from './Card';

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
  id: string;
  align?: 'start' | 'end';
  panelClassName?: string;
  trigger: ReactNode;
  children: ReactNode;
}) {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
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
