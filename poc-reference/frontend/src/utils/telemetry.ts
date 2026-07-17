// Lightweight client telemetry. The event names are the load-bearing part —
// they outlast the demo (roadmap §1.4 "Telemetry"). In the demo we just log;
// a real sink (analytics provider) swaps in behind the same `track` call.

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
  | 'limit_changed';

export function track(
  event: TelemetryEvent,
  props: Record<string, unknown> = {},
): void {
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.debug(`[telemetry] ${event}`, props);
  }
  // Production: forward to the analytics sink here.
}
