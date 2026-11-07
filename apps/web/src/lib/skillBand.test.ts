import { describe, expect, it } from 'vitest';

import { bandAt, bandRange, formatWaited } from './skillBand';

describe('bandAt', () => {
  it('starts at ±100, widens 12 a second, caps at ±800', () => {
    expect(bandAt(0)).toBe(100);
    expect(bandAt(30)).toBe(460);
    expect(bandAt(58)).toBe(796);
    expect(bandAt(59)).toBe(800);
    expect(bandAt(600)).toBe(800);
    expect(bandAt(-5)).toBe(100);
  });
});

describe('bandRange', () => {
  it('centres the band on your rating', () => {
    expect(bandRange(1712, 0)).toEqual([1612, 1812]);
    expect(bandRange(1712, 90)).toEqual([912, 2512]);
  });
});

describe('formatWaited', () => {
  it('reads as a clock', () => {
    expect(formatWaited(7)).toBe('0:07');
    expect(formatWaited(92)).toBe('1:32');
  });
});
