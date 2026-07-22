import { useEffect, useState } from 'react';

import { subscribeToasts, type ToastMessage } from '../../lib/toast';

const DURATION_MS = 4000;

const DOT: Record<ToastMessage['kind'], string> = {
  success: 'bg-green',
  error: 'bg-red',
  info: 'bg-text-secondary',
};

/** Global toast host. Mounted once at the root; sits above the mobile tab bar. */
export function Toaster() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  useEffect(() => {
    const timers = new Set<ReturnType<typeof setTimeout>>();
    const unsubscribe = subscribeToasts((message) => {
      // Keep the last few so a burst never fills the screen.
      setToasts((prev) => [...prev, message].slice(-3));
      const timer = setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== message.id));
        timers.delete(timer);
      }, DURATION_MS);
      timers.add(timer);
    });
    return () => {
      unsubscribe();
      timers.forEach(clearTimeout);
    };
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex flex-col items-center gap-2 px-4 md:inset-x-auto md:bottom-6 md:right-6 md:items-end md:px-0"
      data-testid="toaster"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className="pointer-events-auto flex max-w-sm items-center gap-2.5 rounded-pill bg-panel-raised px-5 py-3 text-sm font-semibold text-text shadow-lg"
        >
          <span
            aria-hidden
            className={`h-2 w-2 shrink-0 rounded-full ${DOT[t.kind]}`}
          />
          {t.text}
        </div>
      ))}
    </div>
  );
}
