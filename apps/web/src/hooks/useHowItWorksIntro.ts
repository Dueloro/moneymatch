import { useEffect, useState } from 'react';

import { useAuth } from '../auth/useAuth';

const LEGACY_KEYS = ['play', 'pools', 'tournament'].map(
  (id) => `mm.dismissed.howitworks.${id}`,
);

export function introKey(userId: string): string {
  return `mm.howitworks.seen.${userId}`;
}

function hasSeen(userId: string): boolean {
  try {
    const ls = window.localStorage;
    return (
      ls.getItem(introKey(userId)) === '1' ||
      LEGACY_KEYS.some((k) => ls.getItem(k) === '1')
    );
  } catch {
    return true;
  }
}

function markSeen(userId: string): void {
  try {
    window.localStorage.setItem(introKey(userId), '1');
  } catch {
    // storage blocked: the note may show again, which is harmless.
  }
}

/**
 * The play-surface explainer shows inline once per user, on whichever play page
 * they open first. It is marked seen as soon as it renders.
 */
export function useHowItWorksIntro(): [boolean, () => void] {
  const { session } = useAuth();
  const userId = session?.user.id;
  const [show, setShow] = useState(() => (userId ? !hasSeen(userId) : false));

  useEffect(() => {
    if (show && userId) markSeen(userId);
  }, [show, userId]);

  return [show, () => setShow(false)];
}
