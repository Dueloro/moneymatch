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

export function takeReturnTo(): string | null {
  const path = peekReturnTo();
  clearReturnTo();
  return path;
}
