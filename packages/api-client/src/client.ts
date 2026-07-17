import createClient, { type Client } from 'openapi-fetch';
import type { paths } from './generated/schema';

export interface ApiClientOptions {
  /** API origin, e.g. http://localhost:8000 */
  baseUrl: string;
  /** Returns the current Supabase access token (or null when signed out). */
  getToken?: () => string | null | Promise<string | null>;
}

/**
 * Typed API client. Every request carries the Supabase JWT (when present) —
 * the server owns all state, so the token is the only client-supplied identity.
 */
export function createApiClient(options: ApiClientOptions): Client<paths> {
  const client = createClient<paths>({ baseUrl: options.baseUrl });

  if (options.getToken) {
    client.use({
      async onRequest({ request }) {
        const token = await options.getToken!();
        if (token) {
          request.headers.set('Authorization', `Bearer ${token}`);
        }
        return request;
      },
    });
  }

  return client;
}

export type ApiClient = Client<paths>;
