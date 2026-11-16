import { describe, expect, it, vi } from 'vitest';

import { env } from './env';

const mocks = vi.hoisted(() => ({
  capture: vi.fn(),
  identify: vi.fn(),
  reset: vi.fn(),
  init: vi.fn(),
}));

vi.mock('posthog-js', () => ({
  default: {
    init: mocks.init,
    capture: mocks.capture,
    identify: mocks.identify,
    reset: mocks.reset,
  },
}));

import { track } from './telemetry';

describe('telemetry sink', () => {
  it('is a no-op when no PostHog key is configured (test env)', () => {
    expect(() => track('entry_queued', { game: 'chess.lichess' })).not.toThrow();
    expect(mocks.capture).not.toHaveBeenCalled();
  });

  it('loads PostHog on first use and delivers events in order', async () => {
    (env as { posthogKey?: string }).posthogKey = 'phc_test';
    track('signup');
    track('match_found', { game: 'chess.lichess' });

    await vi.waitFor(() => expect(mocks.capture).toHaveBeenCalledTimes(2));
    expect(mocks.init).toHaveBeenCalledTimes(1);
    expect(mocks.capture.mock.calls.map((c) => c[0])).toEqual([
      'signup',
      'match_found',
    ]);
  });
});
