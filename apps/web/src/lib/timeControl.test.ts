import { describe, expect, it } from 'vitest';

import type { ProfileSnapshot } from '../hooks/useLinks';
import {
  clockFor,
  defaultSpeed,
  ratingForSpeed,
  timeControlLabel,
} from './timeControl';

const profile = (formats: ProfileSnapshot['formats'], rating: number | null = null) =>
  ({ formats, rating }) as ProfileSnapshot;

describe('timeControlLabel', () => {
  const clocks = [
    { speed: 'blitz', limit_seconds: 300, increment_seconds: 0 },
    { speed: 'classical', limit_seconds: 1800, increment_seconds: 20 },
    { speed: 'bullet', limit_seconds: 90, increment_seconds: 1 },
  ];
  it("names the speed with the server's clock", () => {
    expect(timeControlLabel('blitz', clockFor('blitz', clocks))).toBe('Blitz 5+0');
    expect(timeControlLabel('classical', clockFor('classical', clocks))).toBe(
      'Classical 30+20',
    );
    expect(timeControlLabel('bullet', clockFor('bullet', clocks))).toBe('Bullet 1.5+1');
    expect(timeControlLabel('rapid', clockFor('rapid', clocks))).toBe('Rapid');
    expect(timeControlLabel(null)).toBe('');
  });
});

describe('defaultSpeed', () => {
  it('prefers blitz', () => {
    expect(defaultSpeed(['bullet', 'rapid', 'blitz'])).toBe('blitz');
    expect(defaultSpeed(['bullet', 'rapid'])).toBe('rapid');
    expect(defaultSpeed([])).toBeUndefined();
  });
});

describe('ratingForSpeed', () => {
  const formats = [
    { speed: 'blitz', rating: 1712, games: 900, provisional: false },
    { speed: 'rapid', rating: 1790, games: 40, provisional: true },
  ];

  it('uses the rating for that speed', () => {
    expect(ratingForSpeed(profile(formats), 'rapid')).toEqual({
      rating: 1790,
      from: 'rapid',
      provisional: true,
    });
  });

  it('falls back to the most-played speed, like the server', () => {
    expect(ratingForSpeed(profile(formats), 'classical')?.from).toBe('blitz');
  });

  it('falls back to the profile rating, then to nothing', () => {
    expect(ratingForSpeed(profile([], 1500), 'blitz')?.rating).toBe(1500);
    expect(ratingForSpeed(profile([]), 'blitz')).toBeNull();
    expect(ratingForSpeed(null, 'blitz')).toBeNull();
  });
});
