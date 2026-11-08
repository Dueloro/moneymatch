import { describe, expect, it } from 'vitest';

import { lookingFor } from './tickerCopy';

describe('lookingFor', () => {
  it('names the speed in plain language', () => {
    expect(lookingFor('blitz')).toBe('is looking for a blitz game');
    expect(lookingFor('atomic')).toBe('is looking for an atomic game');
  });

  it('falls back to a game', () => {
    expect(lookingFor(null)).toBe('is looking for a game');
  });
});
