import { createApiClient } from '@moneymatch/api-client';

import { getDeviceId } from './deviceId';
import { env } from './env';
import { getAccessToken } from './supabase';

// One typed client for the whole app; every request carries the Supabase JWT and
// a stable device id (for the server's same-human / collusion guard).
export const api = createApiClient({
  baseUrl: env.apiBaseUrl,
  getToken: getAccessToken,
  getDeviceId,
});
