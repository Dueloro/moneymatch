import { peekReturnTo } from './returnTo';

const KEY = 'mm.linkReturnTo';

/** Where to land after the Lichess round trip; onboarding resumes its own target. */
export function currentLinkReturnPath(): string {
  const { pathname, search } = window.location;
  if (pathname === '/signin') return peekReturnTo() ?? '/play';
  return pathname + search;
}

export function setLinkReturnTo(path: string): void {
  try {
    sessionStorage.setItem(KEY, path);
  } catch {
    /* storage unavailable: fall back to /play */
  }
}

export function peekLinkReturnTo(): string {
  try {
    const path = sessionStorage.getItem(KEY);
    if (path && path.startsWith('/') && !path.startsWith('//')) return path;
  } catch {
    /* ignore */
  }
  return '/play';
}

export function clearLinkReturnTo(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
