// Where to send a player once sign-in and setup finish: an invite link they
// opened signed out stores its path here, so the funnel resumes on it.

const KEY = 'mm.returnTo';

export function setReturnTo(path: string): void {
  sessionStorage.setItem(KEY, path);
}

export function peekReturnTo(): string | null {
  return sessionStorage.getItem(KEY);
}

export function clearReturnTo(): void {
  sessionStorage.removeItem(KEY);
}

/** The stored path, cleared on read so it is used once. For event handlers;
 * a render should peek and clear in an effect. */
export function takeReturnTo(): string | null {
  const path = peekReturnTo();
  clearReturnTo();
  return path;
}
