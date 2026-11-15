import type { PostHog } from 'posthog-js';

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

let loading: Promise<PostHog> | null = null;

// Loaded on first use so the analytics library stays out of the entry bundle.
// Calls chain on one promise, so events still arrive in order.
function withClient(use: (posthog: PostHog) => void): void {
  if (!env.posthogKey) return;
  loading ??= import('posthog-js').then(({ default: posthog }) => {
    posthog.init(env.posthogKey!, {
      api_host: env.posthogHost,
      capture_pageview: false,
      autocapture: false,
      persistence: 'localStorage',
    });
    return posthog;
  });
  void loading.then(use, () => {});
}

export function track(
  event: TelemetryEvent,
  props: Record<string, unknown> = {},
): void {
  if (import.meta.env.DEV) {
    console.debug(`[telemetry] ${event}`, props);
  }
  withClient((posthog) => posthog.capture(event, props));
}

export function identify(userId: string): void {
  withClient((posthog) => posthog.identify(userId));
}

export function resetIdentity(): void {
  withClient((posthog) => posthog.reset());
}
