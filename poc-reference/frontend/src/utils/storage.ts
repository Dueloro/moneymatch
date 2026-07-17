// Best-effort localStorage helpers for the demo's client-side state (wallet,
// contracts). Access is guarded so a disabled/quota-full store never throws.

const PREFIX = 'moneymatch:';

export function loadState<T>(
  key: string,
  fallback: T,
  reviver?: (raw: unknown) => T,
): T {
  if (typeof window === 'undefined') return fallback;
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (raw === null) return fallback;
    const parsed: unknown = JSON.parse(raw);
    return reviver ? reviver(parsed) : (parsed as T);
  } catch {
    return fallback;
  }
}

export function saveState(key: string, value: unknown): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Ignore quota/serialization errors — persistence is best-effort.
  }
}

export function clearState(key: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(PREFIX + key);
  } catch {
    // Ignore.
  }
}
