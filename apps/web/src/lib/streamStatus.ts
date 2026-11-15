import { useSyncExternalStore } from 'react';

let connected = false;
const listeners = new Set<() => void>();

export function setStreamConnected(next: boolean) {
  if (next === connected) return;
  connected = next;
  for (const listener of listeners) listener();
}

export function isStreamConnected(): boolean {
  return connected;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** True while the live event stream is open, so polls can back off. */
export function useStreamConnected(): boolean {
  return useSyncExternalStore(subscribe, isStreamConnected);
}

/** An idle player's next change arrives as a live event, so the queue poll backs off. */
export function queuePollMs(status: string | undefined, live: boolean): number {
  return live && status === 'idle' ? 15_000 : 2000;
}
