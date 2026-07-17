// Client telemetry. The event NAMES are the load-bearing part — they outlast
// the demo and must stay stable (ported from poc-reference telemetry.ts). Phase 6
// points `track` at PostHog (behind VITE_POSTHOG_KEY); with no key it stays
// console-only, so local/dev never sends events (09-phase-6 · deliverable 3).

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
  // Phase 5 acquisition funnel (08-phase-5 · exit criterion 2) + social.
  | 'friend_added'
  | 'challenge_sent'
  | 'challenge_accepted'
  | 'rematch_sent'
  | 'invite_created'
  | 'invite_viewed'
  | 'invite_accepted'
  // Phase 6 activation funnel (gtm-prelaunch §1.2). `landing`/`signup` fire
  // from the sign-in surface; the rest map to existing product moments.
  | 'landing'
  | 'signup'
  | 'account_linked'
  | 'first_contest_joined'
  | 'first_settlement';

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

/** Tie subsequent events to the authenticated user (call after sign-in). */
export function identify(userId: string): void {
  client()?.identify(userId);
}

/** Drop the identity on sign-out so events aren't misattributed. */
export function resetIdentity(): void {
  client()?.reset();
}
