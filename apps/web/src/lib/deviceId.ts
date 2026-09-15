// A stable per-device/browser id, persisted in localStorage. It is sent as
// `X-Device-Id` so the server's same-human / collusion guard can tell when two
// accounts share a device. It is not an identity or a secret — just a random,
// stable token for this browser.

const KEY = 'mm_device_id';

export function getDeviceId(): string | null {
  try {
    let id = localStorage.getItem(KEY);
    if (!id) {
      id =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID()
          : Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem(KEY, id);
    }
    return id;
  } catch {
    // Private mode / storage disabled → no device signal, which is fine (the
    // guard just has one fewer signal; it never blocks for a missing one).
    return null;
  }
}
