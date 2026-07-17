import { createApiClient } from '@moneymatch/api-client';

import { env } from './env';
import { getAccessToken } from './supabase';

// One typed client for the whole app; every request carries the Supabase JWT.
export const api = createApiClient({
  baseUrl: env.apiBaseUrl,
  getToken: getAccessToken,
});
