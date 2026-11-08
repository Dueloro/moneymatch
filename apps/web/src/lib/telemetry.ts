import posthog from 'posthog-js';

import { env } from './env';

export type TelemetryEvent =
  | 'oauth_linked'
  | 'username_claimed'
  | 'lobby_refreshed'
  | 'contest_viewed'
  | 'builder_priced'
  | 'entry_queued'
  | 'match_found'
  | 'match_confirmed'
  | 'contest_settled'
  | 'rake_collected'
  | 'collusion_flagged'
  | 'limit_changed'
  | 'friend_added'
  | 'challenge_sent'
  | 'challenge_accepted'
  | 'rematch_sent'
  | 'invite_created'
  | 'invite_viewed'
  | 'invite_accepted'
  | 'chat_message_sent'
  | 'chat_invite_sent'
  | 'landing'
  | 'signup'
  | 'account_linked'
  | 'first_contest_joined'
  | 'first_settlement'
  | 'contest_filed';

let initialized = false;

function client(): typeof posthog | null {
  if (!env.posthogKey) return null;
  if (!initialized) {
    posthog.init(env.posthogKey, {
      api_host: env.posthogHost,
      capture_pageview: false,
      autocapture: false,
      persistence: 'localStorage',
    });
    initialized = true;
  }
  return posthog;
}

export function track(
  event: TelemetryEvent,
  props: Record<string, unknown> = {},
): void {
  if (import.meta.env.DEV) {
    console.debug(`[telemetry] ${event}`, props);
  }
  client()?.capture(event, props);
}

export function identify(userId: string): void {
  client()?.identify(userId);
}

export function resetIdentity(): void {
  client()?.reset();
}
