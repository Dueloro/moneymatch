import { describe, expect, it } from 'vitest';

import {
  formatPct,
  formatRelativeTime,
  formatPoints,
  formatSignedPoints,
} from './format';

describe('formatPoints', () => {
  it('shows whole points with thousands separators', () => {
    expect(formatPoints(100000)).toBe('100,000 pts');
    expect(formatPoints(1000)).toBe('1,000 pts');
    expect(formatPoints(0)).toBe('0 pts');
    expect(formatPoints(5)).toBe('5 pts');
  });

  it('spells the unit out in sentences', () => {
    expect(formatPoints(1800, { long: true })).toBe('1,800 points');
    expect(formatPoints(1, { long: true })).toBe('1 point');
  });

  it('carries a leading minus on negatives', () => {
    expect(formatPoints(-500)).toBe('-500 pts');
  });
});

describe('formatSignedPoints', () => {
  it('shows an explicit + on positives', () => {
    expect(formatSignedPoints(1800)).toBe('+1,800 pts');
    expect(formatSignedPoints(-1800)).toBe('-1,800 pts');
    expect(formatSignedPoints(0)).toBe('0 pts');
  });
});

describe('formatPct', () => {
  it('rounds a 0..1 share to a whole percent', () => {
    expect(formatPct(0.555)).toBe('56%');
  });
});

describe('formatRelativeTime', () => {
  const now = new Date('2026-07-15T12:00:00Z');
  it('bins recent times', () => {
    expect(formatRelativeTime('2026-07-15T11:59:50Z', now)).toBe('just now');
    expect(formatRelativeTime('2026-07-15T11:55:00Z', now)).toBe('5m ago');
    expect(formatRelativeTime('2026-07-15T09:00:00Z', now)).toBe('3h ago');
    expect(formatRelativeTime('2026-07-13T12:00:00Z', now)).toBe('2d ago');
  });
});
