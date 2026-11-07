import { describe, expect, it, vi } from 'vitest';

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
});
