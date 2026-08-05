import { useCallback, useState } from 'react';

function read(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

/**
 * Remembers a one-time dismissal, so a returning player never pays the tax of
 * scrolling past an explainer they read on their first visit.
 */
export function useDismissed(key: string): [boolean, () => void] {
  const storageKey = `mm.dismissed.${key}`;
  const [dismissed, setDismissed] = useState(() => read(storageKey));
  const dismiss = useCallback(() => {
    try {
      window.localStorage.setItem(storageKey, '1');
    } catch {
      /* private mode: the note just comes back next visit */
    }
    setDismissed(true);
  }, [storageKey]);
  return [dismissed, dismiss];
}
