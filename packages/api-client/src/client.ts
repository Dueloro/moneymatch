import createClient, { type Client } from 'openapi-fetch';
import type { paths } from './generated/schema';

export interface ApiClientOptions {
  /** API origin, e.g. http://localhost:8000 */
  baseUrl: string;
  /** Returns the current Supabase access token (or null when signed out). */
  getToken?: () => string | null | Promise<string | null>;
  /**
   * A stable per-device id sent as `X-Device-Id`, used by the server's
   * same-human / collusion guard (two accounts on one device can't co-enter a
   * contest). Optional; when absent the guard simply has one fewer signal.
   */
  getDeviceId?: () => string | null;
}

/**
 * Typed API client. Every request carries the Supabase JWT (when present) —
 * the server owns all state, so the token is the only client-supplied identity.
 */
export function createApiClient(options: ApiClientOptions): Client<paths> {
  const client = createClient<paths>({ baseUrl: options.baseUrl });

  if (options.getToken || options.getDeviceId) {
    client.use({
      async onRequest({ request }) {
        if (options.getToken) {
          const token = await options.getToken();
          if (token) {
            request.headers.set('Authorization', `Bearer ${token}`);
          }
        }
        if (options.getDeviceId) {
          const deviceId = options.getDeviceId();
          if (deviceId) {
            request.headers.set('X-Device-Id', deviceId);
          }
        }
        return request;
      },
    });
  }

  return client;
}

export type ApiClient = Client<paths>;
