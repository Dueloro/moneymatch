/**
 * Where to send someone after Steam sign-in.
 *
 * Steam OpenID is a full-page redirect: you leave the app entirely and come
 * back on a different route. Returning to a fixed page reads as having lost
 * your place — you clicked "sign in" from one screen and arrive at another,
 * with the thing you were half-way through nowhere in sight.
 *
 * Kept here rather than on either side so a component does not have to import
 * from a page to remember where it was.
 */

const KEY = 'cs2:steam-return-to';

/** Called on the way out, from wherever the sign-in was started. */
export function rememberSteamReturn(path: string): void {
  try {
    sessionStorage.setItem(KEY, path);
  } catch {
    // Private browsing can refuse storage. Losing the return path is a worse
    // landing, not a broken sign-in, so it must never throw.
  }
}

/** Called once on the way back. Consumes the value. */
export function takeSteamReturn(): string | null {
  try {
    const path = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    return path;
  } catch {
    return null;
  }
}
