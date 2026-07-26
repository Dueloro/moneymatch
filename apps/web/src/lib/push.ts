// Web Push (browser) — register the service worker, subscribe against the
// server's VAPID public key, and mirror the subscription to the API. All calls
// no-op gracefully where push isn't supported or configured.

import { api } from './api';

export function isPushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

/** The server's VAPID public key, or null when push isn't configured. */
async function serverPublicKey(): Promise<string | null> {
  const { data, error } = await api.GET('/api/v1/notifications/push/public-key');
  if (error) return null;
  return data?.public_key ?? null;
}

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function registration(): Promise<ServiceWorkerRegistration> {
  const existing = await navigator.serviceWorker.getRegistration();
  return existing ?? navigator.serviceWorker.register('/sw.js');
}

/** True when this browser already has an active push subscription. */
export async function isSubscribed(): Promise<boolean> {
  if (!isPushSupported()) return false;
  const reg = await navigator.serviceWorker.getRegistration();
  if (!reg) return false;
  return (await reg.pushManager.getSubscription()) != null;
}

/** Ask permission, subscribe, and register the subscription with the API.
 * Returns true on success. */
export async function enablePush(): Promise<boolean> {
  if (!isPushSupported()) return false;
  const publicKey = await serverPublicKey();
  if (!publicKey) return false; // push not configured server-side

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return false;

  const reg = await registration();
  await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
  });

  const json = sub.toJSON();
  const keys = json.keys ?? {};
  const { error } = await api.POST('/api/v1/notifications/push/subscribe', {
    body: {
      endpoint: sub.endpoint,
      keys: { p256dh: keys.p256dh ?? '', auth: keys.auth ?? '' },
    },
  });
  return !error;
}

/** Unsubscribe locally and on the server. */
export async function disablePush(): Promise<void> {
  if (!isPushSupported()) return;
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = reg ? await reg.pushManager.getSubscription() : null;
  if (!sub) return;
  const endpoint = sub.endpoint;
  await sub.unsubscribe().catch(() => undefined);
  await api.POST('/api/v1/notifications/push/unsubscribe', { body: { endpoint } });
}
