// Client telemetry. The event NAMES are the load-bearing part — they outlast
// the demo and must stay stable (ported from poc-reference telemetry.ts). The
// real sink (PostHog) swaps in behind `track` in Phase 6 (11-migration §2).

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
  | 'invite_accepted';

export function track(
  event: TelemetryEvent,
  props: Record<string, unknown> = {},
): void {
  if (import.meta.env.DEV) {
    console.debug(`[telemetry] ${event}`, props);
  }
  // Phase 6: forward to the PostHog sink here.
}
